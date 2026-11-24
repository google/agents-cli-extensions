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

"""Sessions kept in Agent Platform Sessions, selected by `SESSION_TYPE`.

`settings.SESSION_TYPE` (from `--session-type` at scaffold time, overridable by
`SESSION_TYPE` in the environment) selects the backend (`in_memory`, `cloud_sql`,
or `agent_platform_sessions`).

When `agent_platform_sessions` is active, a conversation is one Agent
Platform session; its id is the conversation id. On Agent Runtime the agent's
own engine holds the sessions; elsewhere, an engine named by
`AGENT_ENGINE_SESSION_NAME` (default `AGENT_NAME`) does, created on first use.
The session holds two kinds of events:

- Transcript entries, which turns resume from: `TranscriptStore` is the Claude
  SDK's `SessionStore` over them. An entry is JSON text in
  `event_metadata.custom_metadata["transcript"]`, with its subagent subpath
  (`""` for the main transcript) and an append sequence.
- Views: each turn's user message and agent events in the shape of Agent
  Runtime's `async_stream_query` events. They fill the event's named fields
  (author, content, ...) and `raw_event`, so the Google Cloud console shows the
  conversation and `async_get_session` returns it.

The API has no batch append, so each entry is one call. The append sequence is
the append time in milliseconds and is also the event timestamp, so listing by
timestamp gives append order; across instances it relies on their clocks.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import os
import threading
import time
from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

import anyio
from claude_agent_sdk import SessionKey, SessionListSubkeysKey, SessionStoreEntry
from google.api_core.client_options import ClientOptions
from google.api_core.exceptions import AlreadyExists, InvalidArgument, NotFound
from google.auth.transport import mtls
from google.cloud.aiplatform_v1 import (
    AppendEventRequest,
    Content,
    CreateSessionRequest,
    EventMetadata,
    ListEventsRequest,
    ListSessionsRequest,
    Session,
    SessionEvent,
    SessionServiceAsyncClient,
)

from app.app_utils import settings
from app.app_utils.replies import AgentError
from app.app_utils.telemetry.config import agent_name, on_agent_runtime

SESSION_TYPES = ("in_memory", "cloud_sql", "agent_platform_sessions")

_TRANSCRIPT_KEY = "transcript"
# Events need an author and an invocation id; transcript entries get these.
_TRANSCRIPT_AUTHOR = "transcript"

_client: SessionServiceAsyncClient | None = None
_client_loop: asyncio.AbstractEventLoop | None = None
_engine_name: str | None = None
_engine_lock = threading.Lock()
_last_seq: dict[str, int] = {}


class SessionExistsError(Exception):
    """A session with the id exists already."""


class TranscriptStore:
    """The SDK's `SessionStore` over one conversation's session.

    Keys name the CLI's session id; the store serves the one conversation it
    was made for, whatever the key's project or session id.
    """

    def __init__(self, session_id: str) -> None:
        self._session_id = session_id

    async def append(self, key: SessionKey, entries: list[SessionStoreEntry]) -> None:
        subpath = key.get("subpath") or ""
        for entry in entries:
            seq = _next_seq(self._session_id)
            transcript = {"subpath": subpath, "seq": seq, "entry": json.dumps(entry)}
            await _append(
                self._session_id,
                SessionEvent(
                    author=_TRANSCRIPT_AUTHOR,
                    invocation_id=_TRANSCRIPT_AUTHOR,
                    timestamp=_at(seq),
                    event_metadata=EventMetadata(
                        custom_metadata={_TRANSCRIPT_KEY: transcript}
                    ),
                ),
            )

    async def load(self, key: SessionKey) -> list[SessionStoreEntry] | None:
        subpath = key.get("subpath") or ""
        entries = [
            json.loads(transcript["entry"])
            async for transcript, _ in _events(self._session_id)
            if transcript and transcript["subpath"] == subpath
        ]
        return entries or None

    async def exists(self, key: SessionKey) -> bool:
        """Whether the subpath has a transcript, stopping on the first match."""
        subpath = key.get("subpath") or ""
        async for transcript, _ in _events(self._session_id):
            if transcript and transcript["subpath"] == subpath:
                return True
        return False

    async def list_subkeys(self, key: SessionListSubkeysKey) -> list[str]:
        """Subagent transcripts of the session, so they are restored on resume."""
        subpaths = {
            transcript["subpath"]
            async for transcript, _ in _events(self._session_id)
            if transcript and transcript["subpath"]
        }
        return sorted(subpaths)


def session_type() -> str:
    """The configured session backend (`in_memory`, `cloud_sql` or
    `agent_platform_sessions`).

    Reads `SESSION_TYPE` from the environment when set, else `settings.SESSION_TYPE`
    from scaffold time.

    Raises:
        AgentError: `SESSION_TYPE` is not a valid backend name.
    """
    for raw in (os.environ.get("SESSION_TYPE", ""), settings.SESSION_TYPE):
        value = raw.strip()
        if value and value != "none" and "{{" not in value:
            if value not in SESSION_TYPES:
                raise AgentError(
                    f"Invalid SESSION_TYPE={value!r}. "
                    f"Valid options: {', '.join(SESSION_TYPES)}."
                )
            return value
    if os.environ.get("INSTANCE_CONNECTION_NAME") and os.environ.get("DB_PASS"):
        return "cloud_sql"
    if on_agent_runtime():
        return "agent_platform_sessions"
    return "in_memory"


def enabled() -> bool:
    """Whether sessions go to Agent Platform Sessions."""
    return session_type() == "agent_platform_sessions"


async def create_session(
    user_id: str,
    session_id: str | None = None,
    state: Mapping[str, Any] | None = None,
) -> Session:
    """Create a session; the API picks its id when `session_id` is None.

    Raises:
        SessionExistsError: A session with `session_id` exists.
    """
    request = CreateSessionRequest(
        parent=await _engine(),
        session=Session(
            user_id=user_id,
            display_name=agent_name(),
            session_state=dict(state or {}),
        ),
        session_id=session_id or "",
    )
    try:
        operation = await _api().create_session(request=request)
        return await operation.result()
    except (AlreadyExists, InvalidArgument) as err:
        # The API reports a taken id as an invalid argument.
        if isinstance(err, InvalidArgument) and "already exists" not in str(err):
            raise
        raise SessionExistsError(f"Session {session_id} exists already.") from err


async def ensure_session(user_id: str, session_id: str) -> None:
    """Create the user's session unless it exists.

    Raises:
        AgentError: The session is another user's.
    """
    if await get_session(user_id, session_id) is not None:
        return
    try:
        await create_session(user_id, session_id)
    except SessionExistsError as err:
        # Or created by a concurrent turn of the same user.
        if await get_session(user_id, session_id) is None:
            raise AgentError(f"Session {session_id} is another user's.") from err


async def get_session(user_id: str, session_id: str) -> Session | None:
    """The user's session, or None when it doesn't exist or is another user's."""
    try:
        session = await _api().get_session(name=await _name(session_id))
    except NotFound:
        return None
    return session if session.user_id == user_id else None


async def list_sessions(user_id: str) -> list[Session]:
    escaped = user_id.replace("\\", "\\\\").replace('"', '\\"')
    pager = await _api().list_sessions(
        request=ListSessionsRequest(
            parent=await _engine(), filter=f'user_id="{escaped}"'
        )
    )
    return [session async for session in pager]


async def delete_session(session_id: str) -> None:
    operation = await _api().delete_session(name=await _name(session_id))
    await operation.result()
    _last_seq.pop(session_id, None)


async def append_views(session_id: str, views: Sequence[Mapping[str, Any]]) -> None:
    """Append `async_stream_query` events, so readers of the session see them."""
    for view in views:
        event = SessionEvent(
            author=view["author"],
            invocation_id=view["invocation_id"],
            timestamp=_at(_next_seq(session_id)),
            raw_event=dict(view),
        )
        if content := view.get("content"):
            event.content = Content.from_json(
                json.dumps(content), ignore_unknown_fields=True
            )
        if error_code := view.get("error_code"):
            event.error_code = error_code
            event.error_message = view.get("error_message", "")
        await _append(session_id, event)


async def views(session_id: str) -> list[dict[str, Any]]:
    """The views of the session, in the order they were appended."""
    return [view async for _, view in _events(session_id) if view]


def session_json(session: Session, events: Sequence[Mapping[str, Any]]) -> dict:
    """A session as Agent Runtime's session methods return it."""
    return {
        "id": session.name.split("/")[-1],
        "app_name": agent_name(),
        "user_id": session.user_id,
        "state": Session.to_dict(session).get("session_state") or {},
        "events": list(events),
        "last_update_time": session.update_time.timestamp(),
    }


async def _append(session_id: str, event: SessionEvent) -> None:
    await _api().append_event(
        request=AppendEventRequest(name=await _name(session_id), event=event)
    )


async def _events(
    session_id: str,
) -> AsyncIterator[tuple[Mapping[str, Any] | None, dict[str, Any] | None]]:
    """(transcript metadata, view) of each event, oldest first."""
    pager = await _api().list_events(
        request=ListEventsRequest(parent=await _name(session_id), order_by="timestamp")
    )
    async for event in pager:
        data = SessionEvent.to_dict(event)
        metadata = (data.get("event_metadata") or {}).get("custom_metadata") or {}
        yield metadata.get(_TRANSCRIPT_KEY), data.get("raw_event")


def _api() -> SessionServiceAsyncClient:
    # An async client belongs to the event loop it first ran in.
    global _client, _client_loop
    loop = asyncio.get_running_loop()
    if _client is None or _client_loop is not loop:
        _client = SessionServiceAsyncClient(client_options=_client_options())
        _client_loop = loop
    return _client


def _client_options() -> ClientOptions:
    """The regional endpoint, over mTLS when there is a client certificate.

    With one (agent identity on Agent Runtime), tokens are bound to it and only
    accepted over mTLS.
    """
    location = _location()
    if mtls.should_use_client_cert() and mtls.has_default_client_cert_source():
        return ClientOptions(
            api_endpoint=f"{location}-aiplatform.mtls.googleapis.com",
            client_cert_source=mtls.default_client_cert_source(),
        )
    return ClientOptions(api_endpoint=f"{location}-aiplatform.googleapis.com")


def _location() -> str:
    """The engine's region; Agent Runtime doesn't support "global"."""
    if location := os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_LOCATION"):
        return location
    location = os.environ.get("GOOGLE_CLOUD_LOCATION")
    if location and location != "global":
        return location
    # `scaffold create --region` rewrites this default to the project's region.
    return "us-east1"


async def _engine() -> str:
    """The engine whose Agent Platform Sessions hold conversations."""
    if engine_id := os.environ.get("GOOGLE_CLOUD_AGENT_ENGINE_ID"):
        project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        if not project:
            import google.auth

            _, project = await anyio.to_thread.run_sync(google.auth.default)
        if not project:
            raise AgentError(
                "No Google Cloud project; set GOOGLE_CLOUD_PROJECT for Agent Platform Sessions."
            )
        return (
            f"projects/{project}/locations/{_location()}/reasoningEngines/{engine_id}"
        )
    return await anyio.to_thread.run_sync(_resolve_engine)


def _resolve_engine() -> str:
    global _engine_name
    with _engine_lock:
        if _engine_name is None:
            _engine_name = _find_or_create_engine()
        return _engine_name


def _find_or_create_engine() -> str:
    # Imported here so local runs without agent_platform_sessions skip it.
    import agentplatform

    name = os.environ.get("AGENT_ENGINE_SESSION_NAME") or agent_name()
    client = agentplatform.Client(location=_location())
    found = list(client.runtimes.list(config={"filter": f"display_name={name}"}))
    if found:
        return found[0].api_resource.name
    logging.info("Creating Agent Runtime %r for Agent Platform Sessions", name)
    return client.runtimes.create(config={"display_name": name}).api_resource.name


async def _name(session_id: str) -> str:
    if "/" in session_id:
        raise InvalidArgument(f"Invalid session id {session_id!r}.")
    return f"{await _engine()}/sessions/{session_id}"


def _next_seq(session_id: str) -> int:
    seq = max(time.time_ns() // 1_000_000, _last_seq.get(session_id, 0) + 1)
    _last_seq[session_id] = seq
    return seq


def _at(seq: int) -> datetime.datetime:
    return datetime.datetime.fromtimestamp(seq / 1000, datetime.UTC)
