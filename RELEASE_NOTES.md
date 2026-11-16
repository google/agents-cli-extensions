# Release notes

## [1.14.2] - 2026-11-16

- Claude: Pass `--memory-bank` to `agents-cli create` to give the agent
  long-term memory of each user in Vertex AI Memory Bank, which works the way
  ADK's does. The agent recalls the user's memories at the start of each turn,
  learns from each finished turn, and can call a `search_memory` tool. Needs
  `agents-cli` 1.14.0 or later.
  - Memory is per user. For A2A callers without authentication, it lasts one
    conversation, as in ADK.
  - With `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` on, the agent
    records the system prompt the model got, recalled memories included, as
    `gen_ai.system_instructions` on the turn span.
- Claude: Model calls send
  `x-goog-api-client: agents-cli-app/<version>+claude-agent-sdk`, so Google can
  count usage from agents-cli projects. Set `DO_NOT_TRACK=1` or
  `AGENTS_CLI_TELEMETRY=0` to turn it off; your own `ANTHROPIC_CUSTOM_HEADERS`
  are always sent.
- Claude: New projects get a `.env` with the Google Cloud project, location and
  Claude region (`CLOUD_ML_REGION`) defaults.


## [0.1.0] - 2026-11-10

Initial release. The extensions previously shipped in [google/agents-cli](https://github.com/google/agents-cli) under `extensions/` move to this repository under `core/`. The code matches `agents-cli` v1.13.0.

### Extensions

- **Claude** (experimental): scaffolds, runs, evaluates and deploys Claude Agent SDK agents on Claude on Gemini platform, served over A2A. Deploys to `cloud_run` or `agent_runtime`.
- **Langchain** (experimental): scaffolds, runs, evaluates and deploys LangChain agents, LangGraph graphs and Deep Agents, served over A2A. Deploys to `cloud_run` or `gke`; `agent_runtime` has reduced functionality.
