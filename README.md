<div align="center">
  <img src="https://raw.githubusercontent.com/google/agents-cli/main/docs/src/assets/logo_sm.png" alt="agents-cli logo" width="120" />
  <h1>Agents CLI Extensions</h1>
  <p>The central home for extensions for <a href="https://github.com/google/agents-cli"><code>agents-cli</code></a>.</p>

  <p>
    <a href="#available-extensions">Extensions</a> &nbsp;&nbsp;|&nbsp;&nbsp;
    <a href="#installing-an-extension">Install</a> &nbsp;&nbsp;|&nbsp;&nbsp;
    <a href="#managing-extensions">Manage</a> &nbsp;&nbsp;|&nbsp;&nbsp;
    <a href="#development">Development</a> &nbsp;&nbsp;|&nbsp;&nbsp;
    <a href="https://github.com/google/agents-cli-extensions/issues">Issues</a> &nbsp;&nbsp;|&nbsp;&nbsp;
    <a href="https://github.com/google/agents-cli-extensions">Star us</a>
  </p>
</div>

---

An extension overrides or adds `agents-cli` commands, so the agent development lifecycle (scaffold, run, evaluate, deploy) works with something the CLI does not ship with, such as another agent framework.

## Available extensions

| Extension | Description |
|---|---|
| [claude](core/claude) | Claude Agent SDK agents on Claude on Gemini platform, served over A2A. Experimental. |
| [langchain](core/langchain) | LangChain agents, LangGraph graphs and Deep Agents, served over A2A. Experimental. |

See [RELEASE_NOTES.md](RELEASE_NOTES.md) for what changed in each release.

## Prerequisites

Extensions run on top of `agents-cli`, so install it first. Check [Agents CLI](https://github.com/google/agents-cli) for installation steps.

## Installing an extension

Each extension's README explains how to install it. By default an extension is installed at project scope: it is recorded in the project's `agents-cli-extensions.yaml`, or loaded from an `agents-cli-extension.yaml` at the project root, and affects only that project.

### Installing globally (`--global`)

`agents-cli extension add` also accepts `--global`, which installs the extension at user scope instead of into a project:

```bash
agents-cli extension add google/agents-cli-extensions#core/<name>/template --ref <tag|branch|sha> --global
```

A global install has these consequences:

- **It applies to every project on your machine.** The extension is recorded in `~/.config/agents-cli/agents-cli-extensions.yaml` (`%APPDATA%\agents-cli` on Windows) and vendored under `extensions/` in the same directory. Its overrides take effect in every project you run `agents-cli` in, including projects that weren't built for it. For example, an extension that overrides `run` replaces it in your ADK projects too.
- **It works outside a project.** Project scope needs an `agents-cli-manifest.yaml` in the current directory or a parent; user scope does not. Use it when you need an override before a project exists.
- **It isn't shared.** Nothing is committed to a repository, so teammates and CI don't get the extension, and the same command can behave differently on your machine than on theirs.
- **Project scope takes precedence.** If a project-scope extension overrides the same command, the project's version runs. `agents-cli info` and `agents-cli <command> --help` show which one is active.
- **Removal checks project scope first.** `agents-cli extension remove <name>` removes the project-scope copy if there is one, so an extension installed at both scopes needs a second `remove` to drop the global one.

Prefer project scope unless you want the extension active everywhere on your machine.

## Managing extensions

```bash
agents-cli extension list              # active extensions, their scope, and the commands they contribute
agents-cli extension update [<name>]   # move the pin to the latest commit of the tracked ref
agents-cli extension remove <name>     # remove the entry and delete the vendored copy
agents-cli install                     # restore missing or stale vendored copies from the pinned commits
agents-cli info                        # active extensions, their sources, and any conflicts
```

- `extension update` re-resolves the ref that was pinned. A tag or SHA resolves to itself, so nothing changes. To move to a different tag, or to roll back, run `extension add` again with the new `--ref`; it replaces the existing pin. Nothing updates in the background.
- `extension remove` acts on one scope per call, checking the project scope before the user scope. An extension installed at both scopes needs two `remove` calls.
- `agents-cli install` re-fetches vendored copies on a fresh checkout or in CI and never moves a pin.
- If two extensions at the same scope claim one command, the first wins and the later one is ignored. `extension list` and `info` report the conflict.
- `extension list` and `info` also flag an extension whose `requires` range no longer matches the running CLI. Run `agents-cli extension update <name>` to pull a version that supports it.
- `agents-cli --help` marks a command that an extension overrides or adds with `[↑ <extension>]`. `agents-cli <command> --help` shows the extension it comes from, its scope, and the command it runs.
- To run the built-in command instead of an override, prefix it with `AGENTS_CLI_DISABLE_OVERRIDES=1`.

The Agents CLI docs cover [using](https://google.github.io/agents-cli/guide/extensions/using/) and [authoring](https://google.github.io/agents-cli/guide/extensions/authoring/) extensions in more depth.

## Repository layout

```
core/<name>/
├── README.md        # what the extension does and how to use it
├── tests/           # tests for the extension's scripts and overrides
└── template/        # the project template users scaffold from
    ├── agents-cli-extension.yaml      # command overrides, scaffolded into every project
    └── .template/templateconfig.yaml  # read by the CLI, never copied
```

`core/` holds the extensions maintained by the Agents CLI team.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache 2.0. See [LICENSE](LICENSE).
