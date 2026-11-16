# Claude extension

> **Experimental.** Agent Runtime and Cloud Run are the supported deployment targets.

Run a Claude Agent SDK agent through the `agents-cli` lifecycle: scaffold, run, evaluate, and deploy. The template scaffolds an agent that calls Claude on Gemini platform and is served over [A2A](https://a2a-protocol.org), with no ADK dependency. It overrides only the commands that depend on the framework, and the rest, such as `deploy`, `infra`, and `eval grade`, run natively.

| Command | Behavior in a Claude project |
|---------|------------------------------|
| `run` | Runs the agent in-process with a single prompt. |
| `eval generate` | Generates eval traces in the standard `EvaluationDataset` shape, so `eval grade` works unchanged. |
| `publish gemini` | Registers over A2A; refused on Agent Runtime, which needs ADK. |
| `playground`, `eval dataset`, `eval optimize` | Refused with an explanation: the SDK has no local dev UI, and the eval commands need an ADK agent. |

## Installation

Install [Agents CLI](https://github.com/google/agents-cli) first, then scaffold a project from the template:

```bash
agents-cli create my-agent --agent google/agents-cli-extensions/core/claude/template -d cloud_run
cd my-agent && agents-cli install
```

Append `@<tag|branch|sha>` to the template path to pin a version. The project's `agents-cli-extension.yaml` holds the overrides and is loaded automatically, so commit it.

Then try it:

```bash
agents-cli run "What's the weather in San Francisco?"
```

The model named in `app/agent.py` must be enabled in Model Garden for your project, and `run` and `eval` need `GOOGLE_CLOUD_PROJECT` with Application Default Credentials.

Pass `--memory-bank` to `create` (Agents CLI 1.14.0 or later) to give the agent long-term memory of each user in Memory Bank.

The project's coding-agent guide (`AGENTS.md`) and skill (`.agents/skills/agents-cli-claude/`) cover the agent's configuration, sessions, and migrating an existing Claude agent.
