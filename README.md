<div align="center">

# ALENT.RED Core

**The engine room for local AI agents.**

An embedded, cross-platform gRPC server that orchestrates AI agents on your own machine — providers, tools, conversations, and messaging gateways — and hands a clean, language-agnostic API to whatever front-end you put in front of it.

</div>

---

> **Looking for the app?** This repository is the engine only — no screen, no buttons. The desktop application that puts a face on it lives at [alent-red/alent-red-desktop](https://github.com/alent-red/alent-red-desktop). Stay here if you want to build on the core, embed it, or contribute to it.

## 🧠 What is this?

ALENT.RED Core is the brain, not the face.

It runs as a gRPC server — embedded inside a desktop app, launched as a standalone binary, or imported as a Python library — and takes care of everything an AI agent needs to actually _do_ things: talking to LLM providers, persisting conversations, running tools that control the computer or execute code, and bridging to the outside world through chat gateways like Telegram.

It deliberately ships **no UI**. The interface is a stable gRPC contract (with server reflection on, so tools like Postman discover it instantly). Native front-ends — anything that speaks gRPC — drive it. That separation is the whole point: one rigorously-built core, many faces.

Everything lives on your machine. Your conversations are stored in local SQLite; file attachments and images are encrypted at rest with AES-256-GCM; API keys never leave the device. The only network calls are the ones you ask for — to the LLM providers you configure.

## 💡 Why it exists

ALENT.RED Core is built on a single idea: separate the agent's _brain_ from its _face_. The core owns the hard parts — providers, tools, conversations, persistence, gateways — behind one stable contract, leaving each front-end free to be exactly what its platform needs. The result is a foundation you can build a real product on and extend for years.

## ✨ Features

- **Multi-provider LLM support** — Anthropic, OpenAI (Chat Completions _and_ Responses APIs), LM Studio, and fully custom endpoints, behind one uniform interface. Streaming and non-streaming, with tool calls, vision, prompt caching, and reasoning-effort controls.
- **Agents** — configurable units (prompt, model, reasoning depth, verbosity) that own conversations and wield tools.
- **Bricks** — the tool system. An agent's capabilities are composed from bricks:
  - **UI** — control the computer: screenshots, mouse, keyboard, layout-aware typing (macOS & Windows, native, no third-party automation libs).
  - **Code** — run Python in an isolated, `uv`-managed virtual environment.
  - **System** — execute shell commands and surface host context (date, timezone, installed apps).
  - **Scheduler** — schedule deferred self-notifications that wake the agent later.
  - **Vision** — look at image files on the computer (resized, any raster format).
  - **Skills** — reuse Agent Skills already installed on the host (Claude Code, Codex, or the app's own folder).
- **Gateways** — connect external messaging platforms to agents. Telegram is implemented today (long-polling, attachments, profile pictures, whitelist access control); the architecture is built so new platforms slot in cleanly.
- **Streaming everywhere** — conversations and messages publish save/delete events over streaming RPCs, so front-ends stay live without polling.
- **Local-first & encrypted** — SQLite for data, AES-256-GCM for blobs, keys and history never leave the device.
- **Self-healing schema** — the database reconciles itself additively on every boot; no migration files to author or run.
- **Ships as one binary** — compiled standalone with Nuitka; no Python runtime required on the target machine.
- **Truly cross-platform** — macOS, Linux, and Windows, with the platform-specific sharp edges already found and filed down.

## 📖 Concepts

A quick map of the vocabulary, from the outside in:

| Concept          | What it is                                                                                                     |
| ---------------- | -------------------------------------------------------------------------------------------------------------- |
| **Provider**     | A configured connection to an LLM backend (Anthropic, OpenAI, LM Studio, custom).                              |
| **LLM Model**    | A specific model on a provider, with its limits and options (context window, max tokens, image detail, cache). |
| **Agent**        | The actor: a prompt + a model + reasoning/verbosity settings + a set of bricks.                                |
| **Brick**        | A capability an agent can use — a bundle of tools and prompt context (UI, Code, System, Scheduler, Vision, Skills).            |
| **Conversation** | A thread of messages owned by an agent. May originate locally or from a gateway.                               |
| **Message**      | One turn of content: user, AI, internal note, or a tool call/result.                                           |
| **Gateway**      | A bridge to an external messaging platform (e.g. Telegram) that feeds messages in and relays replies out.      |
| **Looper**       | The orchestrator that drives a conversation: calls the LLM, runs tools, loops until done.                      |

## 📦 Requirements

- **Python 3.10+** — installed and managed automatically by the setup script via [`uv`](https://docs.astral.sh/uv/); you don't need a system Python.
- **Git** — on Windows, install [Git for Windows](https://gitforwindows.org/) (it provides the Git Bash environment the helper script runs in).
- **An LLM provider API key** — to do anything useful (Anthropic, OpenAI, or a local LM Studio instance).

That's it. `uv`, the correct Python, the virtual environment, and all dependencies are handled by `./quick.sh setup`.

## 🚀 Quick Start

```bash
# 1. Clone
git clone https://github.com/alent-red/alent-red-core.git
cd alent-red-core

# 2. One-time setup — installs uv, Python 3.10, dependencies, and generates the gRPC code
./quick.sh setup

# 3. Run
./quick.sh run
```

`./quick.sh run` starts the gRPC server on `127.0.0.1:50051` with a local development database, an encrypted blob folder, and a generated encryption key (all created under `dev/` on first run). gRPC **server reflection is enabled**, so you can point a tool like [Postman](https://www.postman.com/) or [grpcurl](https://github.com/fullstorydev/grpcurl) at the port and explore every service without any `.proto` files on hand.

To explore the API, connect a gRPC client to `127.0.0.1:50051` and start with the `Info` service's `GetInfo` call — it returns the running version and process id.

## ⚙️ How It Works

```
                 ┌─────────────────────────────────────────────┐
   gRPC clients  │           ALENT.RED Core            │
   (native UI,   │                                              │
    Postman, …)  │   ┌────────────┐      ┌──────────────────┐   │
        │        │   │   Server   │◄────►│      Looper      │   │
        └───────►│   │ (services) │      │ (conversation    │   │
                 │   └────────────┘      │   processing)    │   │
                 │         │             └────────┬─────────┘   │
                 │         │                      │             │
                 │   ┌─────▼──────┐    ┌──────────▼──────────┐  │
                 │   │  Database  │    │  Managers:          │  │
                 │   │  (SQLite)  │    │  Providers · Bricks │  │
                 │   │   + Blob   │    │  · Gateways         │  │
                 │   │ (encrypted)│    └──────────┬──────────┘  │
                 │   └────────────┘               │             │
                 └────────────────────────────────┼─────────────┘
                                                   │
                              ┌────────────────────┼────────────────────┐
                              ▼                    ▼                    ▼
                         LLM providers        the computer          Telegram
                       (Anthropic, …)      (screen, code, shell)   (and future
                                                                    gateways)
```

A request comes in over gRPC. A **service** validates it and talks to the right **store** (the repository layer over SQLite). When a conversation needs to advance, the **Looper** takes over: it builds the system prompt, asks the **Provider Manager** to call the LLM, streams the response back, and — when the model calls a tool — routes that to the **Brick Manager**, which runs it and feeds the result back into the loop. **Gateways** sit alongside, turning inbound platform messages into conversations and relaying the agent's replies back out.

For the full architecture — every module, every decision, and the reasoning behind it — see [`CLAUDE.md`](CLAUDE.md).

## 🗂️ Project Layout

```
alent-red-core/
├── protos/                 # gRPC contract — the external API (shared across languages)
├── src/alent_red_core/
│   ├── alent_red.py  # AlentRed — the top-level orchestrator
│   ├── server/             # gRPC server + service implementations
│   ├── looper/             # conversation processing loop
│   ├── providers/          # LLM providers + per-API adapters
│   ├── bricks/             # the tool system (ui, code, system, scheduler, vision, skills)
│   ├── gateways/           # external messaging bridges (telegram)
│   ├── database/           # SQLite stores, event buses, schema reconciliation
│   ├── blob/               # encrypted (AES-256-GCM) file storage
│   ├── models/             # domain models (SQLModel + Pydantic)
│   └── common/             # shared utilities (logging)
├── tests/                  # tests (mirrors src structure)
├── quick.sh                # the one script for every dev task
└── CLAUDE.md               # the architecture & conventions contract
```

## 🤝 Contributing

Contributions are welcome. This is a codebase that takes its own quality seriously, so the bar is real — but the tooling makes it easy to hit, and everything you need to know about _how_ the code is structured lives in [`CLAUDE.md`](CLAUDE.md). Read it first; it is the single source of truth for conventions, patterns, and the reasoning behind them.

### Set up your environment

```bash
git clone https://github.com/alent-red/alent-red-core.git
cd alent-red-core
./quick.sh setup
```

### The `quick.sh` workflow

Every development task goes through one script — it wraps `uv`, so you never manage the virtual environment by hand. Run `./quick.sh` with no arguments for an interactive menu, or call a command directly:

| Command                          | What it does                                                                             |
| -------------------------------- | ---------------------------------------------------------------------------------------- |
| `./quick.sh setup`               | First-time setup: installs `uv`, Python 3.10, dependencies, and generates the gRPC code. |
| `./quick.sh run`                 | Run the server on `127.0.0.1:50051` with a local dev database and blob store.            |
| `./quick.sh debug`               | Run under `debugpy`, waiting for a VSCode debugger to attach on port 5678.               |
| `./quick.sh format`              | Format all code with Black (line length 100).                                            |
| `./quick.sh typecheck`           | Type-check with `mypy --strict`.                                                         |
| `./quick.sh test [args]`         | Run the test suite with pytest (extra args pass through, e.g. `-k pattern`).             |
| `./quick.sh proto`               | Regenerate Python code from the `.proto` definitions.                                    |
| `./quick.sh add main\|dev <pkg>` | Add a runtime or dev dependency.                                                         |
| `./quick.sh remove <pkg>`        | Remove a dependency.                                                                     |
| `./quick.sh build`               | Compile a standalone binary with Nuitka.                                                 |
| `./quick.sh release [--force]`   | Build, zip, and upload the host platform's asset to the GitHub release (maintainers).    |
| `./quick.sh clean`               | Remove caches, build artifacts, and the virtual environment.                             |

### Before you open a PR

Three gates, in order — they're the same checks the project holds itself to:

```bash
./quick.sh format      # 1. format
./quick.sh typecheck   # 2. types must pass strict mode, clean
./quick.sh test        # 3. tests must pass
```

Then a smoke check that it still boots: `./quick.sh run`, watch it come up on `:50051`, and stop it (Ctrl-C) — leaving no orphaned processes.

### The standards, in brief

The full rules are in [`CLAUDE.md`](CLAUDE.md), but the headline expectations are:

- **Clean & SOLID** — one class per file, explicit names, short focused methods, no over-engineering.
- **Strict typing** — `mypy --strict` with no explicit `Any` and no `# type: ignore` escape hatches (the few framework-level exceptions are documented).
- **No silent errors** — every exception is either turned into a typed `Error` with the right `ErrorCode` or re-raised. Never swallowed.
- **Consistency over cleverness** — match the patterns already in the codebase so the whole project reads as one hand wrote it.
- **Self-documenting code** — comments explain _why_, never _what_; the code itself says what.

### Working with the gRPC contract

The external API is defined entirely in `protos/`. If you change a `.proto`, run `./quick.sh proto` to regenerate the Python bindings. Generated code lives under `src/alent_red_core/generated/` and is **not** committed — it's rebuilt on every setup. Keep the proto surface minimal and stable; internal implementation details stay out of the contract.

## 🔨 Building &amp; Releasing

`./quick.sh build` compiles a self-contained binary bundle with [Nuitka](https://nuitka.net/) — no Python runtime needed on the target machine. One build produces a binary for one OS + architecture; multi-platform releases mean running the build on each target host.

A few platform notes worth knowing up front (the full reasoning is in [`CLAUDE.md`](CLAUDE.md)):

- **macOS** binaries built with the project's `uv`-managed Python run on every Apple Silicon Mac (deployment target 11.0).
- **Windows** ships as an x86_64 binary; on Windows ARM64 it runs under Prism emulation. This is an ecosystem constraint (no ARM64 builds yet for the Python/`grpcio`/Nuitka chain), not a design choice, and is documented for when that changes.
- **Releasing** (`./quick.sh release`) is a maintainer task: it builds, zips, and uploads the host platform's asset to the GitHub release tagged `v{version}`, creating the release from the matching section of `RELEASE_NOTES.md` on first run. It requires the [GitHub CLI](https://cli.github.com/) authenticated on the project's organization.

## 📬 Contact

- **Anything** — [hello@alent.red](mailto:hello@alent.red).
- **Bugs and feature requests** — open an issue on the relevant repository: [core](https://github.com/alent-red/alent-red-core/issues) or [desktop](https://github.com/alent-red/alent-red-desktop/issues).
- **Security** — please do not open a public issue; email [security@alent.red](mailto:security@alent.red).

## 🔗 Links

- **Architecture &amp; conventions** — [`CLAUDE.md`](CLAUDE.md)
- **Desktop app** — [alent-red/alent-red-desktop](https://github.com/alent-red/alent-red-desktop)
- **Issues** — [github.com/alent-red/alent-red-core/issues](https://github.com/alent-red/alent-red-core/issues)
