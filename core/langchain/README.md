# LangChain extension

> **Experimental.** Cloud Run and GKE are the supported deployment targets.

Run a [LangChain](https://python.langchain.com) agent, LangGraph graph, or Deep Agent through the `agents-cli` lifecycle: scaffold, run, evaluate, and deploy. The template scaffolds a Gemini ReAct agent served over [A2A](https://a2a-protocol.org), with no ADK dependency. It overrides only the commands that depend on the framework, and the rest, such as `deploy`, `infra`, and `eval grade`, run natively.

| Command | Behavior in a LangChain project |
|---------|---------------------------------|
| `playground` | Starts the local LangGraph dev server (`langgraph dev`). |
| `run` | Invokes the compiled graph in-process. |
| `eval generate` | Generates eval traces in the standard `EvaluationDataset` shape, so `eval grade` works unchanged. |
| `publish gemini` | Registers over A2A; refused on Agent Runtime, which needs ADK. |
| `eval dataset`, `eval optimize` | Refused with an explanation: both need an ADK agent. |

## Installation

Install [Agents CLI](https://github.com/google/agents-cli) first, then scaffold a project from the template:

```bash
agents-cli create my-agent --agent google/agents-cli-extensions/core/langchain/template -d cloud_run
cd my-agent && agents-cli install
```

Append `@<tag|branch|sha>` to the template path to pin a version. The project's `agents-cli-extension.yaml` holds the overrides and is loaded automatically, so commit it.

Then try it:

```bash
agents-cli run "What's the weather in San Francisco?"
```

`run` and `eval` call Gemini, so they need credentials: `GOOGLE_CLOUD_PROJECT` with Application Default Credentials, or `GOOGLE_API_KEY` / `GEMINI_API_KEY` for AI Studio.

By default (`--session-type in_memory`), the server keeps A2A thread checkpoints and store items in an in-process `InMemorySaver` and `InMemoryStore` for the lifetime of each container (retained in memory until restart or scale-down, and not shared across replicas). Pass `--session-type cloud_sql` to `create` or `scaffold enhance` on Cloud Run or GKE to persist both in Cloud SQL for PostgreSQL instead.

### Add to an existing project

To use the overrides in a project you already have, install the extension instead of scaffolding:

```bash
agents-cli extension add google/agents-cli-extensions#core/langchain/template --ref <tag|branch|sha>
```

Or install a release from PyPI (see the [root README](../../README.md#installing-from-pypi)):

```bash
agents-cli extension add 'pypi@agents-cli-extensions==<version>#core/langchain/template'
```

This installs only the command overrides, not the template's agent code or dependencies. The project must already provide what the overridden commands use:

- `app/agent.py` exposing `root_agent`, a compiled LangGraph graph (used by `run` and `eval generate`).
- `langgraph.json` pointing at that graph (used by `playground`).
- `langgraph`, `langchain`, and `langgraph-cli[inmem]` in the project's dependencies.

The extension is installed at project scope: it is recorded in `agents-cli-extensions.yaml` and vendored under `extensions/`, so commit both. `extension add` prompts before installing; pass `--yes` to skip the prompt in automation. See the [root README](../../README.md#managing-extensions) for updating and removing extensions.
