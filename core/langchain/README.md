# LangChain extension

Builds, runs, evaluates and deploys LangChain agents, LangGraph graphs and Deep Agents with `agents-cli`. The agent is a compiled LangGraph graph with `messages` state, exported as `root_agent` from `app/agent.py`, and is served over A2A.

**Experimental.** Use `cloud_run` or `gke`. `agent_runtime` serves the app, but `publish gemini`, the Console playground and Console sessions and traces do not work there.

## Usage

Create a new project from the template:

```bash
agents-cli create my-lc-agent --agent google/agents-cli-extensions/core/langchain/template@v0.1.0 -d cloud_run
cd my-lc-agent && agents-cli install
agents-cli run "hello"
```

The default agent is a Gemini ReAct agent (`langchain.agents.create_agent`) with a sample `get_weather` tool. To use a hand-built `StateGraph` or `deepagents.create_deep_agent`, rewrite `app/agent.py` and keep the name `root_agent`. Pre-1.0 LangChain (LCEL chains, `AgentExecutor`) is not supported.

## Command overrides

The scaffolded `agents-cli-extension.yaml` overrides the commands that assume ADK:

| Command | Behavior |
|---|---|
| `playground` | Starts the LangGraph dev server (`langgraph dev`) on port 8080. |
| `run` | Invokes the graph in process with a single prompt. |
| `eval generate` | Generates eval traces by invoking the graph in process. |
| `publish gemini` | Registers the agent over A2A; refused on Agent Runtime, which needs ADK. |
| `eval dataset`, `eval optimize` | Unsupported; the command says so and exits. |

`deploy`, `infra`, `eval grade`, `eval compare` and `eval analyze` run the built-in commands.

The scaffolded project's `.agents/skills/agents-cli-langchain/` skill and its references cover serving, streaming and deployment in detail.
