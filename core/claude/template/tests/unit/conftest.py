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

"""Fixtures shared by the unit tests."""

import datetime
import re

import pytest
from google.api_core.exceptions import AlreadyExists, InvalidArgument, NotFound
from google.cloud.aiplatform_v1 import Session, SessionEvent

from app.app_utils import (
    agent_platform_sessions,
    claude,
    memory_bank,
    project_settings,
    settings,
    turn_options,
    workspaces,
)


class FakeSessionService:
    """Stands in for Agent Platform Sessions' `SessionServiceAsyncClient`."""

    def __init__(self, **_: object) -> None:
        self.sessions: dict[str, Session] = {}
        self.events: dict[str, list[SessionEvent]] = {}

    async def create_session(self, request):
        session_id = request.session_id or str(len(self.sessions) + 1000)
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", session_id):
            raise InvalidArgument(f"Invalid session id {session_id}.")
        name = f"{request.parent}/sessions/{session_id}"
        if name in self.sessions:
            raise AlreadyExists(f"Session {session_id} already exists.")
        session = Session(request.session, name=name)
        session.update_time = datetime.datetime.now(datetime.UTC)
        self.sessions[name] = session
        self.events[name] = []
        return _Operation(session)

    async def get_session(self, name):
        if name not in self.sessions:
            raise NotFound(name)
        return self.sessions[name]

    async def list_sessions(self, request):
        user_id = request.filter.removeprefix('user_id="').removesuffix('"')
        return _pager(s for s in self.sessions.values() if s.user_id == user_id)

    async def delete_session(self, name):
        del self.sessions[name], self.events[name]
        return _Operation(None)

    async def append_event(self, request):
        if request.name not in self.sessions:
            raise NotFound(request.name)
        self.events[request.name].append(request.event)

    async def list_events(self, request):
        events = sorted(self.events[request.parent], key=lambda e: e.timestamp)
        return _pager(events)


class _Operation:
    def __init__(self, result: object) -> None:
        self._result = result

    async def result(self) -> object:
        return self._result


async def _pager(items):
    for item in list(items):
        yield item


@pytest.fixture(autouse=True)
def _hermetic_session_type(monkeypatch):
    """Keep unit tests off remote session stores even in scaffolded projects."""
    monkeypatch.setattr(settings, "SESSION_TYPE", "none")
    monkeypatch.delenv("SESSION_TYPE", raising=False)


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    """Gemini platform env, and workspaces and project root inside tmp_path."""
    # Keep the project's .env out of the tests: load_dotenv() finds it from
    # claude.py's location, not cwd.
    monkeypatch.setattr(claude, "load_dotenv", lambda: None)
    monkeypatch.setenv("ANTHROPIC_VERTEX_PROJECT_ID", "test-project")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Most tests run a bare ClaudeAgentOptions(), which names no model.
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-test")
    for name in (
        "INSTANCE_CONNECTION_NAME",
        "DB_PASS",
        "DB_USER",
        "DB_NAME",
        "SESSION_TYPE",
        "AGENT_ENGINE_SESSION_NAME",
        "BQ_ANALYTICS_DATASET_ID",
        "MEMORY_BANK_ENABLED",
        "MEMORY_BANK_ENGINE_NAME",
        "GOOGLE_CLOUD_AGENT_ENGINE_ID",
        "ANTHROPIC_CUSTOM_HEADERS",
        "DO_NOT_TRACK",
        "AGENTS_CLI_TELEMETRY",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))
    turn_options._cloud_sql_store.cache_clear()
    monkeypatch.setattr(settings, "SESSION_TYPE", "none")
    monkeypatch.setattr(agent_platform_sessions, "_engine_name", None)
    monkeypatch.setattr(agent_platform_sessions, "_client", None)
    monkeypatch.setattr(memory_bank, "_engine_name", None)
    monkeypatch.setattr(memory_bank, "_pending", set())
    monkeypatch.setattr(workspaces, "WORKSPACES", tmp_path / "workspaces")
    monkeypatch.setattr(workspaces, "_workspaces", {})
    project = tmp_path / "project"
    agent_config = project / "agent_config"
    agent_config.mkdir(parents=True)
    monkeypatch.setattr(project_settings, "PROJECT_ROOT", project)
    monkeypatch.setattr(project_settings, "AGENT_CONFIG_DIR", agent_config)
    return agent_config


@pytest.fixture
def sessions_api(monkeypatch) -> FakeSessionService:
    """Agent Runtime's environment, with a fake Agent Platform Sessions API."""
    monkeypatch.setenv("SESSION_TYPE", "agent_platform_sessions")
    monkeypatch.setenv("GOOGLE_CLOUD_AGENT_ENGINE_ID", "123")
    monkeypatch.setenv("GOOGLE_CLOUD_AGENT_ENGINE_LOCATION", "us-central1")
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "test-project")
    for name in ("INSTANCE_CONNECTION_NAME", "DB_PASS", "AGENT_ENGINE_SESSION_NAME"):
        monkeypatch.delenv(name, raising=False)
    fake = FakeSessionService()
    monkeypatch.setattr(
        agent_platform_sessions, "SessionServiceAsyncClient", lambda **_: fake
    )
    monkeypatch.setattr(agent_platform_sessions, "_client", None)
    monkeypatch.setattr(agent_platform_sessions, "_engine_name", None)
    return fake
