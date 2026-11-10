# Claude extension

Builds, runs, evaluates and deploys Claude Agent SDK agents with `agents-cli`. The agent is a `ClaudeAgentOptions` exported as `root_agent` from `app/agent.py`, runs on Claude on Gemini platform, and is served over A2A.

**Experimental.** Supported deployment targets are `cloud_run` and `agent_runtime`.

## Prerequisites

- `agents-cli` installed.
- The Claude model used by the agent (default `claude-haiku-4-5`) enabled for your Google Cloud project in Model Garden.

## Usage

Create a new project from the template:

```bash
agents-cli create my-claude-agent --agent google/agents-cli-extensions/core/claude/template@v0.1.0 -d cloud_run
cd my-claude-agent && agents-cli install
agents-cli run "hello"
```

Or add it to an existing Claude Agent SDK project, from the project root:

```bash
agents-cli scaffold enhance google/agents-cli-extensions/core/claude/template@v0.1.0 --deployment-target cloud_run
```

Pass `--session-type cloud_sql` to keep Claude sessions across instances, and `--bq-analytics` to log each turn to BigQuery Agent Analytics.

## Command overrides

The scaffolded `agents-cli-extension.yaml` overrides the commands that assume ADK:

| Command | Behavior |
|---|---|
| `run` | Runs `root_agent` in process with a single prompt. |
| `eval generate` | Generates eval traces by running `root_agent` in process. `--url` is not supported. |
| `publish gemini` | Registers the agent over A2A; refused on Agent Runtime, which needs ADK. |
| `playground`, `eval dataset`, `eval optimize` | Unsupported; the command says so and exits. |

`deploy`, `infra`, `eval grade`, `eval compare` and `eval analyze` run the built-in commands.

## Known limitations

On `agent_runtime`, `publish gemini`, the Console playground and the Console session and trace views do not work, and Cloud SQL sessions need manual network and database setup. The Anthropic API is not supported; the agent calls Claude through Gemini platform only.

The scaffolded project's `.agents/skills/agents-cli-claude/` skill and its references describe the project layout, serving, sessions and migration from other setups in detail.
