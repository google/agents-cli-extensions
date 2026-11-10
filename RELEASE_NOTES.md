# Release Notes

## v0.1.0

Initial release. The extensions previously shipped in [google/agents-cli](https://github.com/google/agents-cli) under `extensions/` move to this repository under `core/`. The code matches `agents-cli` v1.13.0.

### Extensions

- **claude** (experimental): scaffolds, runs, evaluates and deploys Claude Agent SDK agents on Claude on Gemini platform, served over A2A. Deploys to `cloud_run` or `agent_runtime`.
- **langchain** (experimental): scaffolds, runs, evaluates and deploys LangChain agents, LangGraph graphs and Deep Agents, served over A2A. Deploys to `cloud_run` or `gke`; `agent_runtime` has reduced functionality.

