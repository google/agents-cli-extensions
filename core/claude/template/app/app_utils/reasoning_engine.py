# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Agent Runtime's `:query` and `:streamQuery` methods.

Agent Runtime forwards them to `/api/reasoning_engine` and
`/api/stream_reasoning_engine` with a `{"class_method": ..., "input": {...}}` body.
An ingress Agent Gateway governs only these two methods. They serve the session
methods and `async_stream_query` of ADK's app class, with its inputs and events,
so ADK clients such as `agents-cli run --mode adk` and the Google Cloud console's
playground work. A session id is a conversation id. With
`SESSION_TYPE=agent_platform_sessions`, sessions are kept in Agent Platform
Sessions; otherwise `async_create_session` stores nothing and the other session
methods are unsupported.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Mapping
from contextlib import aclosing
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    Message,
    ResultMessage,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from fastapi import FastAPI, HTTPException, Request, responses
from google.api_core.exceptions import InvalidArgument, NotFound
from opentelemetry import trace

from app.agent import root_agent
from app.app_utils import agent_platform_sessions, memory_bank
from app.app_utils.claude import stream_turn
from app.app_utils.replies import AgentError, result_error, tool_result_text
from app.app_utils.telemetry.config import agent_name, on_agent_runtime


def add_reasoning_engine_routes(app: FastAPI) -> None:
    """Mount the routes Agent Runtime forwards `:query` and `:streamQuery` to."""

    @app.post("/api/reasoning_engine")
    async def query(request: Request) -> dict[str, Any]:
        method, args = await _input(request, _QUERY_METHODS)
        return {"output": await _QUERY_METHODS[method](args)}

    @app.post("/api/stream_reasoning_engine")
    async def stream_query(request: Request) -> responses.StreamingResponse:
        _, args = await _input(request, _STREAM_METHODS)
        message = args.get("message")
        prompt = _prompt(message)
        user_id = _string(args, "user_id")
        if args.get("session_id") is not None:
            session_id = _string(args, "session_id")
            if agent_platform_sessions.enabled():
                await _ensure_session(user_id, session_id)
        elif agent_platform_sessions.enabled():
            # As in ADK's app class, a call without a session runs in a new one.
            session_id = _session_id(
                await agent_platform_sessions.create_session(user_id)
            )
        else:
            session_id = str(uuid.uuid4())
        events = _turn(prompt, message, user_id, session_id)

        async def lines() -> AsyncIterator[str]:
            async with aclosing(events):
                async for event in events:
                    yield json.dumps(event) + "\n"

        return responses.StreamingResponse(lines(), media_type="application/json")


async def _create_session(args: dict[str, Any]) -> dict[str, Any]:
    user_id = _string(args, "user_id")
    session_id = None if args.get("session_id") is None else _string(args, "session_id")
    state = args.get("state")
    if state is not None and not isinstance(state, dict):
        raise HTTPException(400, "state must be an object.")
    if not agent_platform_sessions.enabled():
        return {
            "id": session_id or str(uuid.uuid4()),
            "app_name": agent_name(),
            "user_id": user_id,
            "state": state or {},
            "events": [],
            "last_update_time": time.time(),
        }
    try:
        session = await agent_platform_sessions.create_session(
            user_id, session_id, state
        )
    except agent_platform_sessions.SessionExistsError as err:
        raise HTTPException(409, str(err)) from err
    except InvalidArgument as err:
        raise HTTPException(400, err.message) from err
    return agent_platform_sessions.session_json(session, [])


async def _get_session(args: dict[str, Any]) -> dict[str, Any]:
    _require_sessions()
    user_id, session_id = _string(args, "user_id"), _string(args, "session_id")
    try:
        session = await agent_platform_sessions.get_session(user_id, session_id)
        if session is None:
            raise HTTPException(404, f"Session {session_id} not found.")
        views = await agent_platform_sessions.views(session_id)
    except InvalidArgument as err:
        raise HTTPException(400, err.message) from err
    except NotFound as err:
        raise HTTPException(404, f"Session {session_id} not found.") from err
    return agent_platform_sessions.session_json(session, views)


async def _list_sessions(args: dict[str, Any]) -> dict[str, Any]:
    _require_sessions()
    sessions = await agent_platform_sessions.list_sessions(_string(args, "user_id"))
    # As in ADK's app class, the list has no events.
    return {"sessions": [agent_platform_sessions.session_json(s, []) for s in sessions]}


async def _delete_session(args: dict[str, Any]) -> None:
    _require_sessions()
    user_id, session_id = _string(args, "user_id"), _string(args, "session_id")
    try:
        if await agent_platform_sessions.get_session(user_id, session_id) is None:
            raise HTTPException(404, f"Session {session_id} not found.")
        await agent_platform_sessions.delete_session(session_id)
    except InvalidArgument as err:
        raise HTTPException(400, err.message) from err
    except NotFound as err:
        raise HTTPException(404, f"Session {session_id} not found.") from err


_QUERY_METHODS = {
    "async_create_session": _create_session,
    "async_get_session": _get_session,
    "async_list_sessions": _list_sessions,
    "async_delete_session": _delete_session,
}
_STREAM_METHODS = {"async_stream_query": None}


async def _input(
    request: Request, methods: Mapping[str, Any]
) -> tuple[str, dict[str, Any]]:
    """The class method and `input` of a call to one of `methods`."""
    try:
        body = await request.json()
    except ValueError as err:
        raise HTTPException(400, "The request body is not JSON.") from err
    if not isinstance(body, dict):
        raise HTTPException(400, 'Send {"class_method": ..., "input": {...}}.')
    method = body.get("class_method")
    if method not in methods:
        raise HTTPException(
            404,
            f"Unsupported reasoning_engine method: {method!r}. "
            f"Supported: {', '.join(methods)}.",
        )
    args = body.get("input")
    if args is None:
        return method, {}
    if not isinstance(args, dict):
        raise HTTPException(400, '"input" must be an object.')
    return method, args


async def _ensure_session(user_id: str, session_id: str) -> None:
    """As in ADK's app class, an unknown session id gets a session of its own."""
    try:
        await agent_platform_sessions.ensure_session(user_id, session_id)
    except AgentError as err:
        raise HTTPException(404, f"Session {session_id} not found.") from err
    except InvalidArgument as err:
        raise HTTPException(400, err.message) from err


def _require_sessions() -> None:
    if not agent_platform_sessions.enabled():
        raise HTTPException(
            404,
            "Session management requires SESSION_TYPE=agent_platform_sessions.",
        )


def _string(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str) or not value:
        raise HTTPException(400, f"{key} must be a non-empty string.")
    return value


def _session_id(session: Any) -> str:
    return session.name.split("/")[-1]


def _prompt(message: Any) -> str:
    """The text of a message: a string, or a Content object's text parts."""
    if isinstance(message, str):
        text = message
    elif isinstance(message, dict) and isinstance(message.get("parts"), list):
        text = "".join(
            part["text"]
            for part in message["parts"]
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    else:
        raise HTTPException(
            400,
            'message must be a string or {"role": "user", "parts": [{"text": ...}]}.',
        )
    if not text.strip():
        raise HTTPException(400, "message has no text.")
    return text


async def _turn(
    prompt: str, user_message: Any, user_id: str, session_id: str
) -> AsyncGenerator[dict[str, Any], None]:
    """Run one turn and yield its events; a failed turn ends with an error event.

    With Agent Platform Sessions, the user's message and the events are then
    appended to the session.
    """
    invocation_id = f"e-{uuid.uuid4()}"
    tool_names: dict[str, str] = {}
    failed = False
    turn_span = trace.INVALID_SPAN
    views = [_user_event(invocation_id, user_message)]
    try:
        async with aclosing(
            stream_turn(prompt, root_agent, session_id, user_id)
        ) as stream:
            async for message in stream:
                turn_span = trace.get_current_span()
                if isinstance(message, ResultMessage) and message.is_error:
                    failed = True
                    views.append(_error(invocation_id, result_error(message)))
                    yield views[-1]
                elif event := _event(invocation_id, message, tool_names):
                    views.append(event)
                    yield event
        if on_agent_runtime():
            # Agent Runtime throttles the CPU once the response ends.
            await memory_bank.flush()
    except Exception as e:
        # Log under the ended turn span so the record links to its trace.
        with trace.use_span(turn_span):
            logging.exception("Claude agent turn failed")
        # The SDK raises after an error result too, which already ended the turn.
        if not failed:
            views.append(_error(invocation_id, str(e)))
            yield views[-1]
    await _save_views(session_id, views)


def _user_event(invocation_id: str, message: Any) -> dict[str, Any]:
    if isinstance(message, str):
        parts = [{"text": message}]
    else:
        parts = [
            {"text": p["text"]}
            for p in message["parts"]
            if isinstance(p, dict) and isinstance(p.get("text"), str)
        ]
    return {**_adk_event(invocation_id, "user", parts), "author": "user"}


async def _save_views(session_id: str, views: list[dict[str, Any]]) -> None:
    """Append the turn's events to its session, so readers of it see the turn."""
    if not agent_platform_sessions.enabled():
        return
    try:
        await agent_platform_sessions.append_views(session_id, views)
    except Exception:
        # The transcript that turns resume from is already stored.
        logging.warning("Saving the events of the turn failed", exc_info=True)


def _event(
    invocation_id: str, message: Message, tool_names: dict[str, str]
) -> dict[str, Any] | None:
    """The event for a message: the agent's text and tool calls, or tool results.

    A subagent's messages are left out; its work shows as the tool call that ran it.
    """
    if isinstance(message, ResultMessage):
        # With output_format set, the reply is the structured output.
        if root_agent.output_format is None or message.structured_output is None:
            return None
        parts = [{"text": json.dumps(message.structured_output)}]
        return _adk_event(invocation_id, "model", parts)
    if not isinstance(message, AssistantMessage | UserMessage):
        return None
    if message.parent_tool_use_id or isinstance(message.content, str):
        return None
    parts: list[dict[str, Any]] = []
    for block in message.content:
        if isinstance(block, TextBlock) and block.text:
            parts.append({"text": block.text})
        elif isinstance(block, ToolUseBlock):
            tool_names[block.id] = block.name
            call = {"id": block.id, "name": block.name, "args": block.input}
            parts.append({"function_call": call})
        elif isinstance(block, ToolResultBlock):
            key = "error" if block.is_error else "result"
            response = {
                "id": block.tool_use_id,
                "name": tool_names.get(block.tool_use_id, ""),
                "response": {key: tool_result_text(block)},
            }
            parts.append({"function_response": response})
    if not parts:
        return None
    role = "user" if isinstance(message, UserMessage) else "model"
    return _adk_event(invocation_id, role, parts)


def _error(invocation_id: str, message: str) -> dict[str, Any]:
    return {
        **_adk_event(invocation_id, "model", []),
        "error_code": "AGENT_ERROR",
        "error_message": message,
    }


def _adk_event(
    invocation_id: str, role: str, parts: list[dict[str, Any]]
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "invocation_id": invocation_id,
        "author": agent_name(),
        "actions": {
            "state_delta": {},
            "artifact_delta": {},
            "requested_auth_configs": {},
            "requested_tool_confirmations": {},
        },
        "id": str(uuid.uuid4()),
        "timestamp": time.time(),
    }
    if parts:
        event["content"] = {"parts": parts, "role": role}
    return event
