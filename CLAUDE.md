# ALENT.RED Core

ALENT.RED Core is an embedded, cross-platform (macOS / Linux / Windows) gRPC server for local AI-agent orchestration. It manages providers (Anthropic / OpenAI / LM Studio / custom / etc.), agents, conversations, tools ("bricks"), and external messaging gateways (Telegram etc.), persisting to SQLite with encrypted blob storage. It is consumed as a library or run as a standalone binary.

This file is the working contract for anyone — human or AI agent — contributing to this codebase. It captures the architecture, conventions, and hard-won constraints that keep the project consistent. **These instructions OVERRIDE default behavior; follow them exactly.**

---

## Code Quality Standards (CRITICAL)

This is a world-class codebase. Every change must hold that bar:

1. **Clean & Powerful Code**
   - Write code that delivers high value
   - Organize the project like a work of art
   - Use explicit, clear naming for everything (methods, variables, classes)
   - Follow SOLID principles religiously
   - One file per class
   - Clear methods with well-named parameters
   - **NEVER use nested function definitions (def inside def)** - always use private methods instead

2. **Consciousness Across the Project**
   - Maintain consistency in naming, structure, and patterns
   - Think about the entire project, not just the current file
   - Every piece should feel like it belongs to the same system

3. **Simplicity & Maintainability**
   - Keep code simple and readable
   - Short, focused methods
   - No extra garbage or over-engineering
   - Code should be self-documenting

4. **Edge Cases & Deep Thinking**
   - Always think ahead
   - Manage edge cases proactively
   - Challenge and question assumptions before implementing
   - Consider implications of every decision

5. **Error Handling (CRITICAL)**
   - **NEVER use silent error handling** - All errors must propagate with proper ErrorCode
   - No try/except pass blocks - errors must be handled explicitly
   - Every exception must either be transformed into an Error with appropriate ErrorCode or re-raised
   - Silent failures hide bugs and make debugging impossible

6. **Discriminated Union Pattern (CRITICAL)**
   - **NEVER use `isinstance()` for discriminated unions** - Always use `.type ==` pattern
   - **Internal Python models** - Use `value.type == EnumType.VALUE` for all discriminated unions:
     - `ProviderApiFormat` → `api_format.type == ProviderApiFormatType.ANTHROPIC`
     - `ProviderConfig` → `config.type == ProviderConfigType.OPENAI`
     - `PreferenceValue` → `value.type == PreferenceValueType.STRING`
     - `MessageContent` → `content.type == MessageContentType.USER`
     - `BrickConfig` → `config.type == BrickConfigType.UI`
   - **External SDK types** - Use `.type == "literal_value"` for SDK discriminated unions:
     - Anthropic SDK: `block.type == "text"`, `block.type == "tool_use"`
     - OpenAI Responses SDK: `event.type == "response.output_text.delta"`, `item.type == "message"`
   - **ONLY use `isinstance()` for**:
     - Python built-in types: `isinstance(x, list)`, `isinstance(x, dict)`
     - Exception types: `isinstance(exception, ValueError)`
     - Non-discriminated types without a `.type` field
   - **Benefits**: Better performance, type safety, Pydantic discriminator validation, SDK best practices

7. **Imports (CRITICAL)**
   - **NEVER use inline imports** - All imports must be declared at the top of the file
   - Local-scope imports (inside functions, methods, branches) are forbidden, even for cycle-breaking or OS-gating
   - For circular imports, use `TYPE_CHECKING` blocks at the top
   - For OS-specific modules, gate the module body with `sys.platform` checks but keep imports at the top

---

## Working Principles

### Think First, Code Later

Favor deliberate work over speed:

1. **Discuss** - Explore options and approaches
2. **Challenge** - Question decisions, surface better alternatives
3. **Decide** - Settle on a direction
4. **Execute** - Then write the code

Challenging a design when there is a better path is encouraged. Once a direction is decided, execute it with excellence. Finish one thing completely before moving to the next; avoid assumptions about scope.

### Validating changes

After any code changes:

1. Run `./quick.sh format` to ensure code formatting
2. Run `./quick.sh typecheck` to verify type safety
3. Run `./quick.sh run` and kill after a few seconds to verify it starts correctly
4. Ensure no zombie processes remain

### Maintaining this file

When a structural / architectural / naming / pattern decision is made, implemented, and validated, propose adding it to CLAUDE.md so the contract stays in sync with the code.

---

## Project-Specific Rules

### Documentation

- **NEVER create Markdown files** without explicit request
- **Code should be self-documenting** - Prefer clear code over comments
- **NO CODE EXAMPLES IN CLAUDE.md (CRITICAL)** - Never include code snippets in this file. Code patterns should be learned from the actual codebase, not from documentation files

### Code Comments & Documentation

**Docstrings (Google Style):**

- **Classes** - Always add docstring describing purpose
- **Public methods** - Always add docstring with Args/Returns
- **Private methods** - No docstring unless complex logic
- \***\*main**.py\*\* - No docstring (entry point, self-explanatory)

\***\*init**.py Files:\*\*

- **NO docstrings** - Never add docstrings to **init**.py files
- **NO comments** - Keep them clean, just imports and **all**
- **Package root** (`src/alent_red_core/__init__.py`) - Only exception: contains `__version__` constant
- **Sub-packages** - Import and export relevant modules/classes
- **Pattern**: Import and export classes/functions using `from .module import X` and define `__all__` list

**Inline Comments:**

- **Only for hard decisions** - Explain WHY, not WHAT
- **Important choices** - When a non-obvious approach is used
- **Never for obvious code** - Code should be self-documenting
- **Keep minimal** - Avoid unnecessary comments

### Dependencies & Tools

- **uv** for Python interpreter and dependency management
- **hatchling** as PEP 517 build backend
- **pyproject.toml** - keep it clean and minimal (PEP 621 format)
- **uv.lock** - committed to git for hash verification (sha256 per wheel/sdist)
- **quick.sh** - the development helper script (wraps all `uv` invocations)
- **Black** - Code formatter (uncompromising, line-length 100)
- **mypy** - Static type checker (strict mode + no explicit Any)
  - Models override: `disable_error_code = ["call-overload", "explicit-any"]` for `models/*` AND `gateways.telegram.models.*` (Telegram wire-shape Pydantic models, same limitation) due to SQLModel/Pydantic dynamic metaclasses (Field overloads + dynamic Any types). Scope it narrowly — only Pydantic-model modules, never the logic modules that use them
- **mypy/black/strict-mode rules (CRITICAL)** - NEVER weaken the mypy/black/strict-mode configuration in `pyproject.toml` (strict mode, `disallow_any_explicit`, error-code overrides, etc.) AND NEVER add inline `# type: ignore[...]` comments to silence errors. Both are acceptable only when BOTH conditions are met:
  1. There is no clean code-level fix (e.g., third-party metaclass limitations like SQLModel/Pydantic's `models/*` override, or strict-mode interaction with intentionally untyped generated code).
  2. There is explicit agreement to make the change.

### Logging Standards

**Logger Usage (CRITICAL):**

- Import Logger from `common` module
- Initialize in class `__init__` with module path
- Use structured logging with key=value pairs for all log statements

**Logging Philosophy:**

- **Manual only** - No automatic logging via interceptors
- **Minimal and meaningful** - Log actions, not noise
- **Structured format** - Use key=value pairs, not formatted strings
- **INFO for actions** - Server start/stop, database start/stop, key events
- **DEBUG for details** - Service calls, store operations, internal state
- **Keep it clean** - Don't pollute logs with unnecessary entries

**Logging Patterns:**

- **Logger naming** - Full package path: `server.services.info`, `database.stores.preference_store`, `database.database`, `looper.looper`
- **Operation logging** - Log at start and completion: `{operation}_started` / `{operation}_completed`
- **Include context** - Add relevant data: counts, keys, flags, found status

**Logger Configuration:**

- Static class in `common/logger.py` with `init(log_level, log_format)`, `update()`, `get_logger(name)`
- In-memory config (log_level, log_format) - no persistence needed
- Required parameters for `init()`: log_level and log_format (no defaults, no env vars)
- Runtime changes: `Logger.update(log_level="DEBUG")` (optional params allowed)
- Supports console (colored) and json formats

**Proto Import Fix:**

- protoc generates absolute imports by default
- `quick.sh proto` uses sed to convert to relative imports
- Required for proper Python package structure

### Cross-platform Quirks (CRITICAL)

The project supports macOS, Linux, and Windows. The following pitfalls have been hit and fixed; the rules below prevent regression:

**`strftime` — `%-d` is not portable:**

- GNU/BSD libc (mac/Linux) supports `%-d` (day-without-zero-padding); Microsoft libc (Windows) does not — it would need `%#d` instead
- **Never use `%-` / `%#` in strftime.** Compose the string in Python: `f"{now.strftime('%A, %B')} {now.day}, {now.year}"`

**HTTPS via `urllib.request` — Windows has an empty default trust store:**

- On standalone Python (the kind `uv` ships), `ssl.get_default_verify_paths()` returns `cafile=None, capath=None` on Windows. `urlopen(url)` then fails with `unable to get local issuer certificate`
- **Always pass an explicit SSL context backed by certifi:** `ssl.create_default_context(cafile=certifi.where())`
- `certifi` is a direct dependency for this reason; do not rely on it being transitive through `httpx`

**A freshly downloaded executable can hang in the macOS kernel (CodeBrick `uv`):**

- Seen on macOS 26: the first `uv venv` run on the just-downloaded `uv` finished its work then froze while exiting (state `UE`, uninterruptible, unkillable until reboot). From then on EVERY exec of that same file blocked in `_dyld_start` before its first instruction, while a byte-identical copy of the file, even in the same folder, started instantly. The looper waited forever on `uv pip list` and conversations stayed in `processing` with no error
- **Rule: every tooling subprocess the core spawns outside an LLM-provided timeout gets `_tooling_timeout_seconds` (60 s), and after a timeout NEVER wait for the killed process** (`subprocess.run(timeout=)` does wait after killing and would freeze again; `CodeBrick._run_tooling_command` uses `Popen` + `communicate(timeout)` + `kill()` without `wait()`)
- **Self-repair** - `CodeBrick._run_uv` runs the command, and on timeout repairs the binary then retries once: copy the file next to itself and `os.replace` it over the original (new inode, enough for the observed hang), verify with `uv --version`, and if the copy is unresponsive too, delete and re-download (SHA-256 verified). A second timeout raises `INTERNAL`, which surfaces as a conversation error instead of a silent freeze

**`SetProcessDpiAwarenessContext` on Windows is a one-shot lock:**

- Microsoft's API fails on the second call with `ERROR_ACCESS_DENIED` (process-global DPI mode is set once and frozen for the lifetime of the process)
- **Always call it at module-level, never inside `__init__` or per-call.** Python's `sys.modules` cache guarantees module-level code executes exactly once per process — making the non-idempotent API safe by construction
- Required for any screenshot/input code: without it, Windows reports logical (scaled) coordinates and `BitBlt` copies only that many physical pixels, producing a top-left crop of the real screen at >100% scaling

**`platform.machine()` reflects the emulation layer, not the host:**

- On Windows ARM64 with an x86_64 Python (Prism emulation), `platform.machine()` returns `"AMD64"`, NOT `"ARM64"`. The process cannot detect that it runs on ARM64 hardware without explicit Win32 APIs like `IsWoW64Process2`
- Accept this: branching on `platform.machine() == "ARM64"` to detect Windows ARM is wrong; you will only ever see the emulated arch from inside the process

**Subprocess shell on Windows:**

- `SystemBrick` shells out to `powershell.exe -NoProfile -Command`, NOT bash and NOT pwsh 7+
- PowerShell 5.1 ships with every Windows 10+; pwsh 7+ is not guaranteed installed
- `-NoProfile` skips `$PROFILE` for fast startup and reproducible environment — at the cost of user-defined aliases/modules in the profile. Acceptable tradeoff for an AI automation tool

**CPython compiles its install prefix into the interpreter, and Nuitka ships it:**

- `libpython` and `sysconfig` carry the absolute path the interpreter was installed at (`BINDIR`, `LIBDIR`, `prefix`...). Nuitka copies `libpython` and embeds `sysconfig` into the standalone bundle, so the shipped binary contains the build machine's interpreter path
- With uv's default location (`~/.local/share/uv/python`, `%LOCALAPPDATA%\uv\python`) that path is under the user's home. `quick.sh` exports `UV_PYTHON_INSTALL_DIR` to a shared, user-independent location (`/Users/Shared/uv/python` on macOS, `C:/ProgramData/uv/python` on Windows, `/opt/uv/python` on Linux) for every command, with `UV_PYTHON_PREFERENCE=only-managed` so an interpreter found on PATH is never picked instead, so dev and bundle use the same interpreter and the bundle is independent of the machine
- `cmd_release` enforces it: after the build it scans the bundle for any path under the home folder (`$HOME`, plus `%USERPROFILE%` in both backslash and forward-slash spellings on Windows, since Git Bash's `/c/Users/name` form never appears in a Windows binary) and refuses to publish when one is found. Changing the install dir requires `./quick.sh clean` then `./quick.sh setup` so the interpreter and the venv are recreated

**Bash `> redirect` truncates before the command runs (POSIX, all OS):**

- `cmd > file` creates/truncates `file` to 0 bytes BEFORE `cmd` runs. If `cmd` fails, the file stays empty
- **For any file the next run would skip if it exists:** generate via `cmd > file.tmp && mv file.tmp file`. The atomic `mv` guarantees the final path is either valid or absent
- Pair with `[ ! -s "$file" ]` (size > 0) instead of `[ ! -f "$file" ]` (exists) so a previous failed run is automatically retried

---

## Project Architecture

### Structure

```
alent-red-core/
├── protos/                      # Proto definitions (shared with other languages)
│   ├── common/                  # Shared proto definitions
│   │   └── errors.proto         # Common error codes (ErrorCode enum)
│   ├── info/                    # Info service protos
│   │   ├── messages.proto       # Info service messages
│   │   └── services.proto       # Info service definitions
│   ├── preferences/             # Preferences service protos
│   │   ├── messages.proto       # Preferences messages
│   │   └── services.proto       # Preferences service definitions
│   ├── providers/               # Providers service protos
│   │   ├── messages.proto       # Providers messages
│   │   └── services.proto       # Providers service definitions
│   ├── llm_models/              # LLM models service protos
│   │   ├── messages.proto       # LLM models messages
│   │   └── services.proto       # LLM models service definitions
│   ├── agents/                  # Agents service protos
│   │   ├── messages.proto       # Agents messages
│   │   └── services.proto       # Agents service definitions
│   ├── conversations/           # Conversations service protos
│   │   ├── messages.proto       # Conversations messages
│   │   └── services.proto       # Conversations service definitions
│   ├── bricks/                  # Bricks service protos
│   │   ├── messages.proto       # Bricks messages
│   │   └── services.proto       # Bricks service definitions
│   ├── gateways/                # Gateways service protos
│   │   ├── messages.proto       # Gateways messages (Gateway, GatewayConfig oneof, ConversationSender lives in conversations)
│   │   └── services.proto       # Gateways service definitions
│   └── messages/                # Messages service protos
│       ├── messages.proto       # Messages messages
│       └── services.proto       # Messages service definitions
├── src/alent_red_core/          # Main package (underscore, not dash)
│   ├── __init__.py              # Package root with __version__ and AlentRed export
│   ├── __main__.py              # CLI entry point (argparse, delegates to AlentRed)
│   ├── alent_red.py             # AlentRed top-level orchestrator class
│   ├── common/                  # Shared utilities
│   │   ├── __init__.py
│   │   ├── logger.py            # Structured logging
│   │   └── attached_file_paths_prompt.py  # Shared renderer for text + attached file paths block
│   ├── models/                  # Domain models (SQLModel + Pydantic)
│   │   ├── __init__.py          # Exports all models
│   │   ├── base.py              # Base model with id/timestamps
│   │   ├── types/               # Shared types
│   │   │   ├── __init__.py
│   │   │   ├── model_json.py    # Custom JSON type for Pydantic models
│   │   │   ├── trimmed_non_empty_str.py  # Validated string type
│   │   │   ├── url_str.py       # HTTP/HTTPS-validated string type
│   │   │   └── telegram_username_str.py  # Canonical Telegram username (regex ^[a-z0-9_]{5,32}$)
│   │   ├── preferences/         # Preference domain
│   │   │   ├── __init__.py
│   │   │   ├── preference.py    # Preference entity (SQLModel)
│   │   │   ├── preference_input.py  # DTO for creation/updates
│   │   │   ├── preference_key.py    # Preference key enum (adapter + brick preferences)
│   │   │   ├── preference_value_*.py # Value type models
│   │   │   └── preference_value_type.py # Value type enum
│   │   ├── providers/           # Provider domain
│   │   │   ├── __init__.py
│   │   │   ├── provider.py      # Provider entity (SQLModel)
│   │   │   ├── provider_input.py  # DTO for creation/updates
│   │   │   ├── provider_config_*.py # Config type models (4 types: anthropic, openai, lm_studio, custom)
│   │   │   ├── provider_config_type.py # Config type enum
│   │   │   ├── provider_api_format_type.py  # Api format type enum
│   │   │   ├── provider_api_format_anthropic.py  # Anthropic API format config
│   │   │   ├── provider_api_format_anthropic_cache_ttl.py  # Anthropic cache TTL enum
│   │   │   ├── provider_api_format_openai_chat_completions.py  # OpenAI Chat Completions format
│   │   │   └── provider_api_format_openai_responses.py  # OpenAI Responses format
│   │   ├── llm_models/          # LLM model domain
│   │   │   ├── __init__.py
│   │   │   ├── llm_model.py     # LLM model entity (SQLModel)
│   │   │   ├── llm_model_input.py  # DTO for creation/updates
│   │   │   ├── llm_model_image_detail.py  # Image detail enum (DEFAULT, LOW, HIGH)
│   │   │   └── llm_model_cache.py  # Cache duration enum (DEFAULT, MEDIUM, HIGH)
│   │   ├── agents/              # Agent domain
│   │   │   ├── __init__.py
│   │   │   ├── agent.py         # Agent entity (SQLModel)
│   │   │   ├── agent_input.py   # DTO for creation/updates
│   │   │   ├── agent_reasoning.py  # Reasoning depth enum (DEFAULT, MINIMAL, LOW, MEDIUM, HIGH, XHIGH)
│   │   │   └── agent_verbosity.py  # Verbosity level enum (DEFAULT, LOW, MEDIUM, HIGH)
│   │   ├── conversations/       # Conversation domain
│   │   │   ├── __init__.py
│   │   │   ├── conversation.py  # Conversation entity (SQLModel; gateway origin fields + sender)
│   │   │   ├── conversation_input.py  # DTO for creation/updates
│   │   │   └── conversation_sender.py  # ConversationSender (generic sender identity, JSON)
│   │   ├── gateways/            # Gateway domain
│   │   │   ├── __init__.py
│   │   │   ├── gateway.py       # Gateway entity (SQLModel) + GatewayConfig union
│   │   │   ├── gateway_input.py # DTO for creation/updates
│   │   │   ├── gateway_config_type.py  # Config type enum (TELEGRAM)
│   │   │   └── gateway_config_telegram.py  # Telegram config variant
│   │   ├── bricks/              # Brick domain
│   │   │   ├── __init__.py
│   │   │   ├── brick.py         # Brick entity (SQLModel)
│   │   │   ├── brick_input.py   # DTO for creation/updates
│   │   │   ├── brick_config.py  # Config union type (UI/CODE/SYSTEM/etc.)
│   │   │   ├── brick_config_*.py # Config type models (10 types)
│   │   │   ├── brick_config_ui_move_pointer_geometry.py  # Vision answer shape enum (POINT, BOUNDING_BOX)
│   │   │   ├── brick_config_ui_move_pointer_coordinate_space.py  # Vision coordinate space enum (PIXELS, NORMALIZED_1000)
│   │   │   └── brick_config_type.py # Config type enum
│   │   ├── agent_bricks/        # Agent-Brick junction table
│   │   │   ├── __init__.py
│   │   │   └── agent_brick.py   # AgentBrick entity (many-to-many)
│   │   ├── messages/            # Message domain
│   │   │   ├── __init__.py
│   │   │   ├── message.py       # Message entity (SQLModel)
│   │   │   ├── message_input.py # DTO for creation/updates
│   │   │   ├── message_content.py  # Content union type (Internal/User/AI)
│   │   │   ├── message_content_*.py # Content type models
│   │   │   └── message_content_type.py # Content type enum
│   │   ├── blob/                # Blob data models
│   │   │   ├── __init__.py
│   │   │   └── blob.py          # Blob model (content + metadata)
│   │   ├── llm_responses/       # LLM call results
│   │   │   ├── __init__.py
│   │   │   ├── llm_usage.py     # LlmUsage (normalized input/output token counts of one call)
│   │   │   ├── llm_response.py  # LlmResponse (contents + usage, non-streaming)
│   │   │   └── llm_stream_item.py  # LlmStreamItem (MessageContent | LlmUsage, streaming)
│   │   ├── tools/               # Tool models for bricks
│   │   │   ├── __init__.py
│   │   │   └── tool.py          # Tool model (name, description, parameters_schema)
│   │   └── errors/              # Error handling
│   │       ├── __init__.py
│   │       ├── error.py         # Custom Error exception
│   │       └── error_code.py    # ErrorCode enum
│   ├── providers/               # Provider orchestration
│   │   ├── __init__.py          # Exports BaseProvider, ProviderBuilder, ProviderManager, ProviderManagerBuilder
│   │   ├── base_provider.py     # Abstract base provider (setup/refresh/llm/llm_stream)
│   │   ├── provider_builder.py  # Provider factory
│   │   ├── provider_manager.py  # Provider orchestrator (manages multiple providers)
│   │   ├── provider_manager_builder.py  # ProviderManager factory
│   │   ├── implementations/     # Provider implementations
│   │   │   ├── __init__.py
│   │   │   └── common_provider.py  # CommonProvider (supports Anthropic/OpenAI/LM Studio/Custom)
│   │   └── adapters/            # LLM API adapters
│   │       ├── __init__.py
│   │       ├── base_adapter.py  # Abstract base adapter
│   │       ├── adapter_builder.py  # Adapter factory
│   │       └── implementations/  # Adapter implementations
│   │           ├── __init__.py
│   │           ├── anthropic_adapter.py  # Anthropic Messages API
│   │           ├── openai_chat_completions_adapter.py  # OpenAI Chat Completions
│   │           └── openai_responses_adapter.py  # OpenAI Responses API
│   ├── bricks/                  # Brick implementations
│   │   ├── __init__.py          # Exports BaseBrick, BrickBuilder, BrickManager
│   │   ├── base_brick.py        # Abstract base brick (ABC)
│   │   ├── brick_builder.py     # Brick factory
│   │   ├── brick_manager.py     # Brick orchestrator
│   │   ├── brick_manager_builder.py  # BrickManager factory
│   │   ├── ui/                  # UI brick (computer control)
│   │   │   ├── __init__.py
│   │   │   ├── ui_brick.py      # UIBrick implementation
│   │   │   ├── assets/          # Cursor PNGs (loaded via importlib.resources)
│   │   │   └── system_access/   # OS-specific input/screen access (macOS/Windows)
│   │   ├── code/                # CodeBrick (isolated Python execution via uv venv)
│   │   ├── system/              # SystemBrick (terminal + host context)
│   │   ├── scheduler/           # SchedulerBrick (deferred self-notifications)
│   │   ├── vision/              # VisionBrick (view local image files)
│   │   └── skills/              # SkillsBrick (Agent Skills installed on the host)
│   ├── gateways/                # Gateway orchestration (external messaging channels)
│   │   ├── __init__.py          # Exports BaseGateway, GatewayBuilder, GatewayManager, GatewayManagerBuilder, GatewayReporter
│   │   ├── base_gateway.py      # Abstract base gateway (ABC)
│   │   ├── gateway_reporter.py  # GatewayReporter ABC (manager implements; gateway → manager)
│   │   ├── gateway_builder.py   # Gateway factory (routes on config.type)
│   │   ├── gateway_manager.py   # Gateway orchestrator (bus watch, message render, user-message flow)
│   │   ├── gateway_manager_builder.py  # GatewayManager factory
│   │   └── telegram/            # Telegram gateway (long polling)
│   │       ├── __init__.py
│   │       ├── telegram_gateway.py  # TelegramGateway implementation
│   │       ├── telegram_client.py   # HTTP transport (getUpdates/sendMessage/sendPhoto/getFile/...)
│   │       └── models/          # Telegram wire-shape Pydantic models
│   ├── database/                # Database storage (SQLite/PostgreSQL)
│   │   ├── __init__.py          # Exports Database
│   │   ├── database.py          # Database class with session management + _ensure_schema (additive migration)
│   │   ├── stores/              # Repository pattern stores
│   │   │   ├── __init__.py      # Exports all stores
│   │   │   ├── preference_store.py  # Preference repository
│   │   │   ├── provider_store.py  # Provider repository
│   │   │   ├── llm_model_store.py  # LLM model repository
│   │   │   ├── agent_store.py  # Agent repository
│   │   │   ├── conversation_store.py  # Conversation repository (incl. get_by_gateway)
│   │   │   ├── brick_store.py  # Brick repository
│   │   │   ├── gateway_store.py  # Gateway repository
│   │   │   └── message_store.py  # Message repository
│   │   ├── buses/               # In-process notification buses for streaming RPCs
│   │   │   ├── __init__.py
│   │   │   ├── conversation_bus.py  # Conversation save/delete event bus
│   │   │   └── message_bus.py   # Message save/delete-after event bus
│   │   └── utils/               # Database utilities
│   │       ├── __init__.py      # Exports utilities
│   │       ├── error_handler.py # Database error handler decorator
│   │       └── error_mapper.py  # Database error mapper
│   ├── blob/                    # Blob storage (encrypted file storage)
│   │   ├── __init__.py          # Exports BlobStorage
│   │   └── blob_storage.py      # BlobStorage class with AES-256-GCM encryption
│   ├── seeds/                   # First-run database seeding
│   │   ├── __init__.py          # Exports PreferenceSetup
│   │   └── preference_setup.py  # PreferenceSetup class (seeds default preferences)
│   ├── looper/                  # Conversation processing loop orchestrator
│   │   ├── __init__.py          # Exports Looper, LooperBuilder
│   │   ├── looper.py            # Looper class (setup/refresh/clean/process/pause)
│   │   └── looper_builder.py    # LooperBuilder factory
│   ├── server/                  # gRPC server module
│   │   ├── __init__.py          # Exports Server
│   │   ├── server.py            # Server lifecycle management
│   │   ├── services/            # gRPC service implementations
│   │   │   ├── __init__.py      # Exports all services
│   │   │   ├── info_service.py  # Info service implementation
│   │   │   ├── preferences_service.py  # Preferences service implementation
│   │   │   ├── providers_service.py  # Providers service implementation
│   │   │   ├── llm_models_service.py  # LLM models service implementation
│   │   │   ├── agents_service.py  # Agents service implementation
│   │   │   ├── conversations_service.py  # Conversations service implementation
│   │   │   ├── bricks_service.py  # Bricks service implementation
│   │   │   ├── gateways_service.py  # Gateways service implementation
│   │   │   ├── messages_service.py  # Messages service implementation
│   │   │   └── blob_service.py  # Blob service implementation (Save/Read)
│   │   └── utils/               # Server utilities
│   │       ├── __init__.py
│   │       ├── error_mapper.py  # Exception to (grpc.StatusCode, ErrorCode, error_message) mapper
│   │       ├── error_handler.py # @handle_grpc_errors decorator
│   │       └── error_code_converter.py  # Python ErrorCode → proto ErrorCode converter (shared)
│   └── generated/               # Auto-generated code (DO NOT EDIT)
│       └── proto/               # Generated from .proto files (NOT committed; regenerated on setup)
├── tests/                       # Tests mirror src structure
├── RELEASE_NOTES.md             # One "## {version}" section per version, read by quick.sh release
├── quick.sh                     # Dev commands (setup, run, proto, add, remove, clean)
└── pyproject.toml              # Standard Python packaging
```

### Key Decisions Made

**Project Structure:**

- **src/ layout** - Separates code from config, catches packaging bugs early
- **protos/ at root** - Shared proto definitions for multi-language support
- **Nested proto structure** - Each service/domain gets its own folder (info/, common/)
- **Separated messages from services** - `messages.proto` + `services.proto` pattern per domain
- **generated/ directory** - Auto-generated code isolated from source, mirrors proto structure
- **Generated code NOT committed** - `generated/` in .gitignore, regenerated during setup/proto commands

**Technology Choices:**

- **uv** - Single tool for Python interpreter management, venv creation, dependency install, and hash-locked lockfile
- **hatchling** - PEP 517 build backend; auto-discovers package data, no `setup.py`
- **uv-managed Python 3.10** - Portable, per-project interpreter with `MACOSX_DEPLOYMENT_TARGET=11.0` (required for back-compat Nuitka binaries on Apple Silicon)
- **gRPC with grpc.aio** - Async/await for modern Python (community standard 2024+)
- **grpcio-reflection** - Service discovery for development tools (Postman, etc.)
- **SQLModel** - ORM for database models (built on SQLAlchemy + Pydantic)
- **SQLAlchemy async** - Async database operations with aiosqlite
- **Pydantic** - Data validation and DTOs (non-database models)
- **Python 3.10+** - Minimum version
- **Cross-platform** - Designed to be called by native front-ends: Swift (macOS) / C# (Windows)

**Code Conventions:**

- **Relative imports** - `from .module import X` for easy project renaming
- **Google-style docstrings** - IDE-friendly, community standard
- **Type hints** - Always use for clarity and IDE support
- **Version management** - Single source of truth in `__init__.py`
- **No default parameters** - Unless explicitly required
- **No environment variables** - Never rely on environment variables for configuration
- **String validation (CRITICAL)**:
  - All string fields MUST be trimmed and non-empty (use TrimmedNonEmptyStr)
  - Never accept "" as valid - reject with validation error
  - Avoid ambiguity between "" and None - use explicit None for absence
  - Client responsibility to trim before sending - we NEVER auto-trim
  - We are strict validators, not data transformers

**gRPC Service Conventions:**

- **Service naming** - Follow Google standard: nouns without "Service" suffix (e.g., `service Info`, not `service InfoService`)
- **File naming** - Service implementation files named `{service}_service.py` (e.g., `info_service.py` for `Info` service)
- **Class naming** - Implementation class matches service name exactly (e.g., `class InfoService(InfoServicer)`)
- **Services folder** - All gRPC service implementations live in `server/services/`
- **Descriptor-based registration** - Services registered using proto `ServiceDescriptor` for reflection
- **Logger naming** - Follow full package structure (e.g., `server.services.info` for InfoService)
- **Proto/Python mapping** - Service methods convert between proto messages and Python models

**Error Handling:**

- **Custom Error exception** - `models/errors/error.py` with `ErrorCode` enum
- **Error mapper utility** - `server/utils/error_mapper.py` maps Python exceptions to gRPC errors
- **Error handler decorator** - `server/utils/error_handler.py` provides `@handle_grpc_errors` decorator
- **Decorator pattern** - Applied to all gRPC service methods for automatic error handling
- **gRPC status code strategy** - Always use `grpc.StatusCode.UNKNOWN` for all application errors
- **Error code in metadata** - Pass custom `ErrorCode` via gRPC trailing metadata as `error-code` for client localization
- **Error message in metadata (CRITICAL)** - For our own `Error` exceptions only, pass the message text via trailing metadata as `error-message`. Never for non-`Error` exceptions (ValueError, IntegrityError, raw Python errors, etc.) — would leak server-side details
- **Message sanitization** - `details` field on `context.abort` stays hardcoded to `"Operation failed"`; sensitive text only flows through trailing metadata where the client opts in to read it
- **Error code → proto enum conversion** - `server/utils/error_code_converter.py` provides `python_error_code_to_proto(python_error_code)` for serializing stored `ErrorCode` values (e.g., `Conversation.error_code`, `MessageContentTool.error`) into proto enum integers
- **Proto ErrorCode enum** - Defined in `protos/common/errors.proto`, shared across all languages (Swift/C#)
- **Python ErrorCode enum** - Mirrors proto enum in `models/errors/error_code.py`
- **Available error codes** - `UNKNOWN`, `INTERNAL`, `INVALID_ARGUMENT`, `NOT_SUPPORTED`, `NOT_ALLOWED`, `NOT_FOUND`, `DUPLICATED`, `RELATION_VIOLATION`, `RATE_LIMIT`, `INVALID_RESPONSE`, `TIMEOUT`
- **Error code priority (CRITICAL)** - Error must describe what happened in its scope, follow this order:
  1. `INVALID_ARGUMENT` - Invalid input from caller (validation failure, malformed data)
  2. `NOT_SUPPORTED` - Feature/enum/option not implemented (new enum value, unsupported API format)
  3. `NOT_ALLOWED` - Operation violates business logic/rules (cannot change preference type, processing in progress)
  4. `NOT_FOUND` - External resource missing from external storage (DB record, file, preference in database)
  5. `INVALID_RESPONSE` - External resource has unexpected format (wrong type from DB, malformed API response, invalid file format)
  6. `INTERNAL` - Internal state not initialized when it should be (e.g. an instance variable / adapter / client that setup should have set but is None)
  7. `DUPLICATED`, `RELATION_VIOLATION`, `RATE_LIMIT`, `TIMEOUT` - Specific cases, keep as-is
- **NOT_FOUND vs INTERNAL distinction (CRITICAL)**:
  - `NOT_FOUND` - A referenced entity is absent. This covers both EXTERNAL storage (a DB record / file is missing) AND a manager's in-memory instance registry (a provider/brick/gateway id not in `self._providers` / `self.bricks` / `self.gateways`). The managers treat their instance maps as registries of known entities, so a miss is "that entity is not loaded" → `NOT_FOUND`, consistent across all managers
  - `INVALID_RESPONSE` - External data has an unexpected shape (wrong type from DB, malformed API response, an invariant the DB shouldn't allow)
  - `INTERNAL` - State that setup should have initialized is still None/unset (e.g. a client/adapter instance variable accessed before setup). NOT for "entity not in a registry map" — that is `NOT_FOUND`
  - Examples: Preference missing from DB → `NOT_FOUND`; Provider id missing from `self._providers` → `NOT_FOUND`; TelegramGateway's `self._client` is None before setup → `INTERNAL`
- **Exception mapping**:
  - `Error` (custom) → use `error.code` directly
  - `ValueError` → `INVALID_ARGUMENT`
  - `IntegrityError` (UNIQUE) → `DUPLICATED`
  - `IntegrityError` (FOREIGN KEY) → `RELATION_VIOLATION`
  - `IntegrityError` (NOT NULL) → `INVALID_ARGUMENT`
  - Other IntegrityError → `INTERNAL`
  - Unknown exceptions → `INTERNAL`
- **Type safety** - Decorator uses ParamSpec and TypeVar for full type preservation
- **Nuitka compatible** - Decorator pattern compiles correctly with Nuitka

**Models Architecture:**

- **Domain-driven structure** - Organize by domain (preferences, providers, errors) in separate folders
- **Plural directories, singular files** - `models/preferences/` contains `preference.py`, `preference_key.py`, etc.
- **Base model pattern** - All database models inherit from `Base` (SQLModel with id, created_at, updated_at)
- **SQLModel for entities** - Database-backed models use SQLModel (combines SQLAlchemy + Pydantic)
- **Pydantic for DTOs** - Non-database models (like `PreferenceInput`) use Pydantic BaseModel
- **Custom types in models/types/** - Reusable validated types:
  - `ModelJSON` - For storing Pydantic models as JSON columns
  - `TrimmedNonEmptyStr` - Validated string (trimmed, non-empty), use like `HttpUrl`
- **One model per file** - Each class in its own file for clarity and maintainability
- **Type hints everywhere** - Full type coverage for all models
- **Discriminated union pattern** - For polymorphic models (e.g., PreferenceValue, ProviderConfig):
  - Use `Literal[EnumType.VALUE] = EnumType.VALUE` for type field in each variant
  - Union wrapped with `Annotated[Union[...], Discriminator("type")]`
  - Follows same pattern as Preference/Provider models
- **Validation strategy**:
  - Entity models (SQLModel) - Structure only, no validation logic
  - Config/value models (Pydantic) - Include validation (Field constraints, custom validators)
  - Never trust client data - always validate trimmed strings, URLs, required fields
  - Use Pydantic `AfterValidator` for reusable custom validation logic
- **Attached file paths (agent and message)** - `Agent.attached_file_paths` and `MessageContentUser.attached_file_paths` are lists of `TrimmedNonEmptyStr`, paths only (never file contents), folders allowed, existence never checked. The agent list is a JSON column (`ModelJSON(list[TrimmedNonEmptyStr])`; `ModelJSON` accepts dicts and lists). Both render through `AttachedFilePathsPrompt.render(text, paths, prefix, separator)` with the `ATTACHED_FILE_PATH_PROMPT_PREFIX` / `_SEPARATOR` preferences: `text + prefix + (separator + path)*`, so every path carries the separator. Seeds are `\n\nAttached files:` and `\n` (one path per line; preference strings cannot end with a space, so no bullet). The looper renders the agent prompt with its paths before substituting `{{AGENT_PROMPT}}`; the three adapters render user messages the same way. No dedicated placeholder: the block belongs to the agent prompt
- **Conversation context size** - `Conversation.context_tokens_count: int | None` is system-written (looper), client-read (proto READ message only, preserved by the service on update, None on create). After every LLM call the looper stores `usage.input + usage.output`: the input is everything the conversation held when the call was sent, the output now belongs to the history. It is reset to None whenever the history changes without a call: a message edit (`Messages.Save` with an id, after `delete_after`) and a split (the new conversation starts at None). Nullable column, so the additive reconciler adds it to existing databases on boot (verified: rows kept, column added)
- **Streaming persistence (CRITICAL)** - The looper persists streamed content PROGRESSIVELY on one message id so `WatchSaves` and the gateways see it grow: `MessageContentAi.processing` (`true` while streaming, `false` on the final save, the same flag `MessageContentTool` already has) and `_partial_save_interval_seconds = 0.15` throttle the partial saves. An AI message is created at the first chunk containing non-blank text (a blank-only turn, e.g. whitespace before a tool call, persists nothing), a tool request is created at its first chunk with the partial `request` and completed by the flush that executes it. The text is never trimmed or reformatted. On cancellation (`pause`), the partial content is closed with `processing=false`: an AI text keeps what was received, a tool request stays without response and adapters replay it with the no-response prompt. `GatewayManager` ignores AI saves while `processing` is true, so Telegram receives one final message. Adapters emit chunks with `processing=False` (chunks are not persisted messages; the looper owns the flag)
- **Non-trimmed string fields (deliberate)** - `MessageContentAi.text` and `MessageContentTool.request` are plain `str` (NOT `TrimmedNonEmptyStr`) because streaming concatenates partial chunks; trimming mid-stream deltas would corrupt them. All other user-facing strings use `TrimmedNonEmptyStr`
- **Foreign key relationships (CRITICAL)** - For related entities:
  - Foreign key always on "many" side of one-to-many relationships
  - `Relationship` declared on the model for ORM metadata (FK constraints, cascade), but DO NOT traverse relationships from outside the session that loaded the parent — see "Relationship access pattern" below
  - Direct FK access always available without loading (e.g., `llm_model.provider_id` returns UUID without any query)
  - CASCADE strategy: `ondelete="CASCADE"` and `onupdate="CASCADE"` for dependent entities
  - SET NULL strategy: `ondelete="SET NULL"` and `onupdate="SET NULL"` for soft-coupled entities (e.g., `Conversation.agent_id`, `Agent.llm_model_id`)
  - Use SQLAlchemy `ForeignKey` with `sa_column` for constraint configuration
  - Composite unique constraints for domain-specific uniqueness (e.g., `provider_id + model_id`)
  - Use `TYPE_CHECKING` imports to avoid circular dependencies
- **FK column nullability (CRITICAL)** - When using `sa_column=Column(ForeignKey(...))`, SQLAlchemy's `Column` defaults to `nullable=True`, which **overrides** SQLModel's "Python type → NOT NULL" inference. So:
  - If the Python type says `UUID` (non-Optional), you MUST pass `nullable=False` explicitly inside the `Column(...)` call to get NOT NULL in the DDL
  - If the Python type says `UUID | None`, the implicit nullable default is correct (no explicit flag needed)
  - This trap silently produces nullable FK columns when you wanted NOT NULL. Always verify the DDL matches the Python type
- **Relationship access pattern (CRITICAL)** - Never traverse SQLAlchemy relationships outside the session that loaded the parent (causes `DetachedInstanceError`). Instead:
  - Fetch the FK column from the parent (e.g., `conversation.agent_id` — scalar, no query)
  - Use the appropriate store to fetch the related entity by ID (e.g., `database.agents.get(agent_id=conversation.agent_id)`)
  - This convention applies to all code under `looper/`, `bricks/`, `providers/`, and services
  - Models still declare `Relationship` for ORM metadata, but code must not depend on lazy loading
- **Index and constraint naming (CRITICAL)** - Database identifiers follow explicit prefixes:
  - Regular indexes: `index_{table}_{col1}_{col2}` (e.g., `index_conversation_updated_at`, `index_conversation_agent_id_updated_at`)
  - Unique constraints: `unique_{table}_{col1}_{col2}` (e.g., `unique_llm_model_provider_id_model_id`, `unique_message_conversation_id_sequence`, `unique_agent_brick_agent_id_brick_id`, `unique_gateway_name_agent_id`, `unique_conversation_gateway_id_gateway_external_id`)
  - Both prefixes are full words, not abbreviations — explicit over short
- **Gateway domain** - `Gateway` (SQLModel) has `name`, `send_detailed_messages` (bool), `error_code`/`error_message` (system-owned health), `config` (GatewayConfig discriminated union, one variant TELEGRAM today), `agent_id` (FK `agent.id`, CASCADE/CASCADE — a gateway with no agent is meaningless, NOT NULL). Unique `(name, agent_id)`. `GatewayConfigTelegram`: `token`, `allow_all`, `allowed_user_names: list[TelegramUsernameStr]` (whitelist is stored-by-name only, lowercase-canonical; matching/`@`-handling is the front-end's job, the model is a strict validator)
- **ConversationSender** - A flat, generic, platform-agnostic Pydantic value object (`name`, `user_name`, `picture_file_key`, all `str | None`), stored on `Conversation.sender` via ModelJSON. NOT a discriminated union — one shape the UI renders identically for every gateway
- **Conversation gateway origin (CRITICAL)** - `Conversation` gains `gateway_id` (FK `gateway.id`, SET NULL/SET NULL), `gateway_external_id: str | None` (the platform's chat id, kept as a string so any gateway sets its own identifier), `sender: ConversationSender | None`. Routing keys are FLAT COLUMNS (not embedded JSON) because the lookup `(gateway_id, gateway_external_id)` must be indexed — JSON cannot be indexed by inner field. On gateway delete, SET NULL nulls `gateway_id` but `gateway_external_id`/`sender` SURVIVE as history (deliberate — the conversation remembers its origin). The unique constraint `(gateway_id, gateway_external_id)` allows unlimited regular `(NULL, NULL)` conversations (NULL tuples never collide) while enforcing one conversation per gateway chat
- **Server-owned (system-written, client-read) fields** - `Gateway.error_code`/`error_message` and `Conversation.gateway_id`/`gateway_external_id`/`sender` are written only by the system (the gateway runtime / looper), never settable by the gRPC client. Pattern: the field is in the proto READ message but NOT the proto INPUT message; the Python input DTO carries it so internal code can write it; the service `Save` preserves it on update by fetching the existing row (fetch-and-preserve), and sets it to None/null on create. Mirrors how `Conversation.processing`/`error_code` already work

**Storage Architecture:**

- **Two storage modules** - `database/` for relational data (SQLite/PostgreSQL), `blob/` for encrypted file storage
- **Repository pattern** - Each domain gets a "store" in `database/stores/`
- **Store naming** - `{domain}_store.py` (e.g., `preference_store.py`)
- **Store location** - `database/stores/{domain}_store.py`
- **Database class** - Central database management in `database/database.py`
- **Session management** - Context manager pattern for async sessions (auto-commit/rollback)
- **Store registration** - Stores attached to Database instance (e.g., `database.preferences`)
- **Logger naming** - Full path: `database`, `database.stores.preference_store`, `blob`
- **Async everywhere** - All database operations use async/await
- **SQLAlchemy expressions** - Use SQLAlchemy select/where for queries, not raw SQL
- **Foreign key filtering (mypy workaround)** - When filtering by FK column in WHERE clauses:
  - Use `column("column_name")` from sqlalchemy instead of direct attribute access
  - Example: `select(LlmModel).where(column("provider_id") == provider_id)`
  - This helps mypy understand column expressions when using `sa_column=Column(ForeignKey(...))`
  - Known limitation with SQLModel/SQLAlchemy type stubs
- **Ordering pattern** - Use `desc(column("field_name"))` for descending order instead of `.desc()` method (mypy compatibility)
- **Sequence-based pagination (CRITICAL)** - For domains with potentially large per-parent histories (e.g., Messages):
  - **Per-conversation** monotonic integer `sequence` column on Message (NOT global, NOT auto-increment)
  - Sequence is computed by the store at insert time: `SELECT COALESCE(MAX(sequence), 0) + 1 FROM message WHERE conversation_id = ?`
  - UNIQUE constraint on `(conversation_id, sequence)` guards against duplicate values
  - On UNIQUE collision (concurrent inserts in the same conversation), the store catches the `IntegrityError` matching the constraint name `unique_message_conversation_id_sequence`, rolls back, and retries indefinitely — any other `IntegrityError` propagates
  - Query DESC by sequence, then reverse results to return chronological order (oldest first)
  - Client concatenates: new_messages + existing_messages for easy prepending
  - Supports `before_message_id` (excluded) and `count` pagination parameters
  - Sequence is internal-only — never exposed in proto definitions
- **Gateway lookups** - `ConversationStore.get_by_gateway(gateway_id, gateway_external_id)` returns the single conversation for a gateway origin (backed by the unique constraint) — the find step of the find-or-create when a user message arrives
- **MessageBus / ConversationBus optional filter** - Both buses' `watch_saves(conversation_id=None)` accept an optional filter: a concrete id watches one conversation (used by the gRPC `Watch*` RPCs), `None` watches all (used by the GatewayManager to observe every save). `MessageBus.watch_saves` was made optional-filter to match `ConversationBus` exactly

**Schema Migration (additive reconciliation):**

- **No versioned migrations, no migration files** - The schema is reconciled on every boot by `Database._ensure_schema(connection)` (run inside `run()`). It is generic (driven by `SQLModel.metadata` vs the live DB), additive-only, and stateless — no `schema_version` table, no per-change scripts to author or remember
- **What it does** - Snapshots existing table names, runs `create_all` (new tables + their indexes), then for each PRE-existing table adds: missing columns via `ALTER TABLE ADD COLUMN` (DDL rendered via SQLAlchemy `CreateColumn`), missing unique constraints via `CREATE UNIQUE INDEX IF NOT EXISTS` (SQLite cannot `ALTER` a table-level UNIQUE onto an existing table, but an equivalent unique index works), and missing indexes via `CREATE INDEX IF NOT EXISTS`
- **Why additive-only** - A blind metadata-vs-DB diff safely handles new tables / new nullable columns / new indexes — never renames, type changes, or NOT-NULL-without-default (those need ordered human migrations and would lose data). It is idempotent (re-running alters nothing) and data-preserving (existing rows untouched)
- **The contract (CRITICAL)** - New columns MUST be nullable or have a default. SQLite physically cannot add a NOT-NULL column to a table that already has rows. This keeps the additive reconciler safe for existing users; a rename/type-change is the only case that would need a manual migration step

**Proto Conventions:**

- **Google types** - Use `google.protobuf.Timestamp` for timestamps, `google.protobuf.Duration` for durations
- **File naming** - Always `messages.proto` (plural) + `services.proto` (plural) per domain
- **Package structure** - `alent_red_core.{domain}` (e.g., `alent_red_core.info`)
- **UUID fields** - Always use `string` type for UUID fields (industry standard, human-readable, cross-language compatible)
- **Discriminated unions (CRITICAL)** - When modeling unions in proto:
  - Create separate message types for each variant
  - DO NOT include `type` field in variant messages (redundant - `oneof` field name already discriminates)
  - Wrap variants in a parent message with `oneof` (no explicit type field at wrapper level)
  - Proto's `oneof` field name serves as the discriminator
  - Python models KEEP `type: Literal[EnumType.VALUE]` for Pydantic validation (internal only)
  - Proto stays clean - no redundant type fields in JSON output
  - Separation: internal implementation ≠ external protocol
- **Internal vs External (CRITICAL)** - Never expose internal implementation details:
  - Proto defines external protocol - keep it clean and minimal
  - Python models can have extra fields for validation/business logic (e.g., `type` for Pydantic, `llm_id`/`turn_id` on `MessageContentTool`)
  - Business logic stays in store methods, never in proto
  - External protocol must remain stable even if internal implementation changes

**Adapter Architecture:**

- **Base adapter interface** - All adapters inherit from BaseAdapter with two abstract methods:
  - `llm()` - Non-streaming generation, returns list of MessageContent
  - `llm_stream()` - Streaming generation, yields MessageContent chunks
- **Constructor signature** - All adapters use consistent parameter order:
  - `api_format: ProviderApiFormat` - API format configuration (first parameter)
  - `base_url: str` - Base URL for API endpoint
  - `api_key: str | None` - API key for authentication
- **Method signature** - Both llm() and llm_stream() accept parameters in this order:
  - `system_prompt: str | None` - System instruction for the AI or None
  - `messages: list[MessageContent]` - Conversation history
  - `image_blobs: dict[str, Blob]` - Dictionary mapping image file keys to Blob objects
  - `tools: list[Tool] | None` - List of available tools or None
  - `model_id: str` - Model identifier
  - `max_output_tokens_count: int` - Maximum tokens to generate
  - `top_p: float` - Nucleus sampling parameter
  - `image_detail: LlmModelImageDetail` - Image detail level (DEFAULT/LOW/HIGH)
  - `cache: LlmModelCache` - Cache duration (DEFAULT/MEDIUM/HIGH)
  - `reasoning: AgentReasoning` - Reasoning depth (DEFAULT/MINIMAL/LOW/MEDIUM/HIGH/XHIGH)
  - `verbosity: AgentVerbosity` - Verbosity level (DEFAULT/LOW/MEDIUM/HIGH)
- **ProviderApiFormat discriminated union** - Three variant types instead of single enum:
  - `ProviderApiFormatAnthropic` - Anthropic-specific configuration with reasoning budget tokens (1024-65536) and cache TTL enums
  - `ProviderApiFormatOpenAiChatCompletions` - OpenAI Chat Completions format (currently empty)
  - `ProviderApiFormatOpenAiResponses` - OpenAI Responses format (currently empty)
- **ProviderApiFormatAnthropicCacheTtl enum** - Constrains Anthropic cache TTL to valid values:
  - `DEFAULT = "default"` - No caching (default behavior)
  - `MIN_5 = "5m"` - 5 minute cache
  - `HOUR_1 = "1h"` - 1 hour cache
- **Three API patterns** - Each adapter implements provider-specific message format conversion:
  - Anthropic: content blocks (TextBlock, ToolUseBlock) in assistant messages, ToolResultBlockParam in user messages
  - OpenAI Chat Completions: tool_calls array on assistant message + separate tool role messages
  - OpenAI Responses: flat items array with function_call and function_call_output items
- **Provider-specific parameter mapping**:
  - Anthropic: cache → cache*control on last message (using api_format.cache_medium_ttl/cache_high_ttl), reasoning → thinking.budget_tokens (using api_format.reasoning*\*\_budget_tokens)
  - OpenAI Chat Completions: reasoning → reasoning_effort (for reasoning models)
  - OpenAI Responses: reasoning → reasoning.effort, verbosity → text.verbosity
- **Responses non-stream parsing** - `OpenAiResponsesAdapter.llm()` skips `output_text` blocks with empty text: some backends emit an empty message item alongside a `function_call`
- **LM Studio counts cached tokens inside `input_tokens`** - unlike Anthropic. `ProviderApiFormatAnthropic.input_tokens_include_cache` (Python-only, never in the proto; the service sets False for CUSTOM, `CommonProvider` sets True for `LM_STUDIO` and False for `ANTHROPIC`) tells `AnthropicAdapter._build_usage` whether to add the cache fields. Without it the context size doubled on LM Studio at the second turn (verified: 2831 → 5668 with the bug, 2831 → ~2850 fixed). LM Studio's prompt cache does hit through the core (turn 1 ≈ 9 s for a 2.8k-token prompt, next turns ≈ 1 s), with `cache_read_input_tokens` reported in 256-token blocks
- **LM Studio speaks the Anthropic format without a key** - `LM_STUDIO` builds the Anthropic adapter on the configured `base_url` (LM Studio serves `/v1/messages`; verified with `qwen/qwen3.5-9b`) with `api_key=None`. The Anthropic SDK refuses a request whose auth header is empty or missing (`TypeError "Could not resolve authentication method"`, surfaced as `UNKNOWN`) unless the header is EXPLICITLY omitted, so `AnthropicAdapter` passes `extra_headers={"X-Api-Key": Omit()}` on every call when no key is configured. Never fall back to an empty-string key
- **Anthropic non-streaming goes through the SDK stream (CRITICAL)** - `AnthropicAdapter.llm()` collects the final message with `messages.stream(...).get_final_message()`, never `messages.create()`. The SDK refuses a non-streaming request whose `max_tokens` could exceed its 10-minute window (above roughly 21k tokens) with a plain Python exception, which surfaced as `UNKNOWN` on every non-streamed call of a model configured with a large `max_output_tokens_count`, including the UIBrick vision call
- **Usage is part of every adapter answer (CRITICAL)** - `llm()` returns `LlmResponse(contents, usage)` and `llm_stream()` yields `LlmStreamItem` (`MessageContent` chunks, then exactly one `LlmUsage` as the LAST item; a stream that ends without usage is `INVALID_RESPONSE`). `LlmUsage.input_tokens_count` is NORMALIZED to the whole prompt: Anthropic reports `input_tokens` EXCLUDING prompt-cache reads and writes, so the adapter adds `cache_creation_input_tokens` and `cache_read_input_tokens` (verified equal to `count_tokens`); OpenAI Chat Completions and Responses already include cached tokens in `prompt_tokens` / `input_tokens` (`cached_tokens` is a subset), so they are passed as is. Streaming sources: Anthropic `get_final_message().usage` after the event loop, Chat Completions `stream_options={"include_usage": True}` (usage rides the last chunk), Responses the `response.completed` event. The chain `BaseProvider` → `CommonProvider` → `ProviderManager` carries the same types; the looper and the UIBrick vision call read `.contents`
- **Tool call support** - All adapters support tools via `_build_tools_param()` helper method:
  - Converts Tool list to provider-specific tool format
  - Returns `Omit()` when no tools provided
  - All adapters convert MessageContentTool to/from provider-specific formats
- **Turn-based grouping** - turn_id links multiple tool calls from same AI response turn
- **Pending pattern** - Queue tool outputs/results/responses, flush at message boundaries or turn_id changes
- **Progressive streaming** - Tool arguments accumulate incrementally and yield partial updates
- **Type safety** - Use provider SDK types (no type ignore comments) for proper validation
- **Error mapping** - Consistent exception handling across all providers (rate limits, timeouts, auth, validation)
- **Image injection** - Adapters handle images from MessageContentToolResponse.image_file_keys:
  - Anthropic: Base64-encoded ImageBlockParam in ToolResultBlockParam (supports jpeg, png, gif, webp)
  - OpenAI Chat Completions: Separate user message with ChatCompletionContentPartImageParam (data URI format) using pending_user_message_for_images pattern
  - OpenAI Responses: Directly in FunctionCallOutput.output as ResponseInputImageContentParam (data URI format)
  - All adapters use image_blobs dictionary parameter to access encrypted images
  - LlmModelImageDetail parameter controls OpenAI vision detail level (auto/low/high)
- **OpenAI Responses specific** - Proper semantic message handling:
  - AI messages (what assistant said) use ResponseOutputMessageParam with role="assistant" and empty string for id field
  - User/Internal messages use Message (input) with role="user"
  - No module alias imports - use explicit imports from openai.types.responses and submodules

**Bricks Architecture:**

- **BaseBrick abstract class** - All bricks inherit from BaseBrick (ABC) with abstract `get_identifier()` method
- **Constructor signature** - All bricks accept: `config`, `looper` (Looper, for triggering conversation processing from inside the brick — used by SchedulerBrick to deliver notifications), `bricks` (BrickManager), `providers` (ProviderManager), `database`, `blob`
- **Instance variables** - Bricks have access to: `self._config`, `self._looper`, `self._bricks`, `self._providers`, `self._database`, `self._blob`
- **BrickManager constructor** - Accepts `looper`, `providers` (ProviderManager), `database`, `blob` and forwards them to every brick it builds
- **Public bricks access** - BrickManager exposes `self.bricks` (public dict) for brick-to-brick access
- **Lifecycle methods** - `setup()`, `refresh(config)`, `clean()` for resource management (refresh receives updated config)
- **Hook methods** - `before_loop()`, `after_loop()` called by conversation orchestrator
- **Interface methods** - `get_prompt()`, `get_tools()`, `handle_tool_request()` (all return None by default)
- **Tool name prefixing** - BrickManager prefixes tool names with brick identifier (e.g., `ui_move_mouse`)
- **Duplicate detection** - BrickManager enforces unique tool names across all bricks (INVALID_RESPONSE error)
- **Factory pattern** - BrickBuilder creates brick instances, BrickManagerBuilder creates manager
- **Brick folder structure** - Direct folders under `bricks/` (e.g., `bricks/ui/`), no `implementations/` parent
- **Identifier pattern** - Each brick has `_identifier` class variable, `get_identifier()` returns it
- **Typed configs** - Each brick accepts its specific config type (e.g., UIBrick accepts BrickConfigUI), discriminated union narrows type
- **Tool parameters** - Passed as JSON string (not dict), brick parses as needed
- **Preference-based separator** - BRICK_PROMPT_SEPARATOR preference controls prompt concatenation
- **Preference loading** - BrickManager loads tool/prompt separators via `_load_preferences()` in setup/refresh
- **Agent-brick resolution** - BrickManager's `get_prompt`, `get_tools`, `handle_tool_request` resolve a conversation's bricks via `database.bricks.get_all(agent_id=conversation.agent_id)` — never via relationship traversal. Caller (looper) is responsible for ensuring `conversation.agent_id` is set; manager raises `INVALID_ARGUMENT` if missing

**VisionBrick (local image files):**

- One tool, `view_images(paths)`: absolute paths, list without bound, `~` expanded. Every path is validated BEFORE any rendering; if at least one fails, nothing is rendered and the tool answers with a TEXT listing each failing path with its reason (`path must be absolute`, `file not found`, `not a file`, `unsupported format (HEIC)`, `unsupported format (not a raster image)`, `cannot be decoded`), the supported formats, and the instruction to convert or fix and call again. Text instead of `Error` because a tool `Error` only persists its code, so the model would never see the guidance (see the `MessageContentTool.error_message` open item)
- Format control is on CONTENT, never on extension: Pillow sniffs the bytes, then `image.format` must be in the whitelist `PNG, JPEG, GIF, WEBP, BMP, TIFF`. PDF/DOCX/SVG are not raster images and are refused; HEIC is detected by its `ftyp` brand so the message names it (Pillow needs `pillow-heif` to read it; not added yet)
- Rendering mirrors screenshots but with its own constants (resolution, quality, format may diverge later, so nothing is shared with UIBrick): EXIF orientation applied, transparency flattened on white, first frame of animated GIFs, downscale only (never upscale) to 1920 px max edge, JPEG quality 80, saved as a blob named after the source file. Images are returned in the order requested

**SkillsBrick (Agent Skills on the host):**

- Implements the open Agent Skills format (agentskills.io): one folder per skill, a `SKILL.md` starting with a YAML front matter (`name`, `description`) then Markdown instructions. `pyyaml` is a main dependency for the front matter. `name` must match `^[a-z0-9]+(-[a-z0-9]+)*$` (max 64) and defaults to the folder name (Claude Code allows omitting it); `description` is required. Invalid skills are skipped with a warning, never fatal
- **Roots are hardcoded per OS, no config** (`BrickConfigSkills` is empty), resolved per conversation in this priority order: `agent` (`<app>/skills-agents/<agent_id>/`, WRITABLE, private to the agent and kept across its conversations; a sibling of the shared folder so an existing shared skill can never collide with the container), `app` (`<app>/skills/`, WRITABLE, shared by every agent, unchanged since the first release so existing installs keep working), `claude` (`~/.claude/skills`, Claude Code personal skills, read-only), `agents` (`~/.agents/skills`, Codex CLI user skills, read-only, verified against OpenAI docs: Codex does NOT use `~/.codex/skills`). `<app>` is `~/Library/Application Support/AlentRed` on macOS and `%LOCALAPPDATA%\AlentRed` on Windows. Only immediate subfolders are scanned (hidden folders and folders without `SKILL.md` skipped, so Claude's `synced/` container is not descended). Same name in two roots gives two ids, both listed; two copies with an identical `SKILL.md` body are listed once under the first root. Deleting an agent never deletes its folder (user files)
- **Skill id is `label/name`** (`claude/pdf`, `app/my-skill`), so the same skill name across tools never collides. Progressive disclosure: `get_prompt` rescans the roots on EVERY turn (a skill dropped while the app runs appears next turn) and lists `id: description` plus the roots with their writable flag and how to create a skill; `load_skill(id)` returns the body and the absolute folder so the agent reads references or runs scripts through the System brick. No file-reading tool in this brick (the terminal does it). Unknown id answers a TEXT listing the available ids (tool `Error` would lose the message)

**UIBrick pointer moves (coordinates and description):**

- Two agent-facing tools replace the former single `move_pointer`: `move_pointer_coordinates(screen_id, image_width, image_height, x, y)` and `move_pointer_description(screen_id, element_description)`. Both end in `_move_pointer_to_ratio`, the single move path: a relative position `(rx, ry)` in [0, 1] multiplied by the capture size, then `system_access.move_pointer`. **No forced screenshot after a move** (product decision): the tools answer `{"moved": true}` like `click_pointer` answers `{"clicked": true}`, and the agent takes a screenshot itself when it wants to verify. The brick prompt tells the agent to prefer coordinates and fall back to description after a miss
- **The ratio is the contract (CRITICAL)** - A vision model returns coordinates in the pixel space of the image it PERCEIVES, which may differ from the image we SENT (Anthropic standard tier downsizes above 1568 px / 1568 patches, high-resolution tier above 2576 px / 4784 patches, OpenAI has its own rules). Verified on Haiku 5.5, Sonnet 5.5 and GPT Luna: models declare the perceived size exactly, so `x / width`, `y / height` is stable across every sent size and across server-side resizing. Never divide by the sent size, never announce our resolution to the model, never ask for normalized coordinates from Claude (documented as unreliable). Screenshots stay at 1920 px max edge: legible, and under the strict 2000 px per-side limit that Anthropic applies to requests with more than 20 images (conversation histories hit that quickly)
- **`move_pointer_description` calls the configured vision model in-process** - `BrickConfigUI.move_pointer_llm_model_id` references an LlmModel, hence its provider and credentials; the brick goes through `ProviderManager.llm` like the looper. The capture (1920 px, no cursor) is saved as a temporary blob and sent inside a synthetic exchange (`MessageContentUser` + a `MessageContentTool` carrying the image key, the only way images travel in message contents), with one tool `locate_element` the model must call; the blob is deleted in `finally`. A text answer without the tool call is `INVALID_RESPONSE`; `found: false` returns a not-found text to the agent without moving the pointer; provider errors (RATE_LIMIT, ...) surface as tool errors and the conversation continues
- **Config drives the vision tool schema, never the agent tools** - `move_pointer_geometry` (`POINT` → `x, y`; `BOUNDING_BOX` → `x1, y1, x2, y2`, the brick takes the center) and `move_pointer_coordinate_space` (`PIXELS` → the model also reports `width, height` and the brick divides; `NORMALIZED_1000` → Qwen-style 0..1000, the brick divides by 1000). Both are required (no defaults, proto `UNSPECIFIED` rejected); the desktop proposes `POINT` + `PIXELS`. The agent calling `move_pointer_description` never sees these settings nor the `locate_element` tool

**UIBrick event tag (overlay passthrough mechanism):**

- `UIBrick._event_tag = 0x414C454E54524544` (ASCII `"ALENTRED"` packed as a 64-bit integer)
- Written to every synthetic **mouse** event's OS user-data field:
  - macOS: `kCGEventSourceUserData` (field index `42`) via `CGEventSetIntegerValueField`
  - Windows: `dwExtraInfo` on the `MOUSEINPUT` struct, declared as `c_void_p` (ULONG_PTR-sized) so it carries 64 bits on x64
- **Mouse only — NOT keyboard, NOT move_pointer.** Keyboard events route by focus (not coordinates) so the overlay rarely sees them; move_pointer is `CGWarpMouseCursorPosition` / `SetCursorPos` (direct cursor warps, not events) — they carry no metadata field
- **Purpose:** the Tauri overlay sits always-on-top and would consume every AI click. With the tag, the overlay reads `kCGEventSourceUserData` / `dwExtraInfo`, sees the magic, and lets the event fall through to the window underneath. Real user input (untagged) reaches the overlay normally. Two streams of events coexist without race conditions
- **macOS overlay note:** on macOS the overlay must use **geometric click-through** (`NSWindow.ignoresMouseEvents` with carve-outs for interactive regions), NOT `CGEventTap`. Event taps are global; returning NULL from a tap callback deletes events system-wide, not "from your window." The tag is still set on macOS for diagnostics / future use, but routing relies on geometry
- **Windows overlay note:** the overlay's `WndProc` reads `GetMessageExtraInfo()` and lets tagged events fall through (e.g. by returning `HTTRANSPARENT` from `WM_NCHITTEST`)

**Gateways Architecture:**

Gateways connect external messaging platforms (Telegram, future WhatsApp/Discord) to agents. A conversation can originate **from** a gateway (a user messages the bot) and the agent's messages flow **back** to it (the bot replies). Gateways are global instances, one per `Gateway` row, managed like bricks/providers.

- **BaseGateway abstract class** - All gateways inherit from BaseGateway (ABC). Constructor: `config` (GatewayConfig), `blob` (BlobStorage), `gateway_id` (UUID — the gateway knows its own id), `reporter` (GatewayReporter). Instance variables: `self._config`, `self._blob`, `self._gateway_id`, `self._reporter`
- **Minimal dependency injection** - Gateways get ONLY `config` + `blob` + their `gateway_id` + a narrow `reporter`. They do NOT get the looper, database, or the manager. All common logic (find-or-create conversation, message rendering, looper triggering) lives in the manager, not the gateway. The gateway is a thin platform-adapter
- **Lifecycle methods** - `setup()`, `refresh(config)`, `clean()` (no-op defaults, overridable). `refresh` reassigns `self._config`; a concrete gateway may fully restart (e.g. TelegramGateway restarts its poll loop on config change)
- **Manager → gateway methods** (the manager tells the gateway to act, keyed by `gateway_external_id`): `handle_message(gateway_external_id, text, image_file_keys)` (pre-rendered text + image blob keys — the gateway does NOT interpret content), `handle_conversation_processing(gateway_external_id, processing)` (e.g. typing indicator), `handle_conversation_error(gateway_external_id, error)`. All optional no-op defaults
- **GatewayReporter (gateway → manager interface)** - A narrow ABC the `GatewayManager` **implements directly** (no separate binding/adapter class — collapsed to one). The gateway holds the manager typed as `GatewayReporter`, so it sees ONLY: `handle_message(gateway_id, gateway_external_id, content, sender)` (report a user message) and `handle_error(gateway_id, error)` (report/clear a gateway-level error; `None` clears). The gateway passes its OWN `gateway_id` on each call (it knows its id). This gives least-privilege without a per-gateway binding object
- **GatewayManager** - Constructor: `looper`, `database`, `blob`. Owns `self.gateways: dict[UUID, BaseGateway]` (public). Lifecycle `setup()`/`refresh()`/`clean()` mirror BrickManager (build/diff/remove). Loads `BRICK_TOOL_NAME_SEPARATOR` via `_load_preferences()` in setup/refresh (for tool-name rendering). Starts two bus-watching tasks in `setup` (conversation saves, message saves), cancels them in `clean`
- **Dict holds instances, NOT data (CRITICAL)** - `self.gateways` holds live gateway _instances_ only. ALL gateway _data_ (`send_detailed_messages`, `agent_id`, config) is read from the DB at use time, never cached in the manager. This keeps the DB the single source of truth and avoids drift (e.g. toggling `send_detailed_messages` takes effect immediately with no cache to refresh)
- **Save dispatch (bus-driven)** - Manager subscribes to `ConversationBus`/`MessageBus` `watch_saves()` (no filter = all). On conversation save: resolve gateway, call `handle_conversation_processing`, and `handle_conversation_error` if `error_code` set. On message save: skip USER content (that came from the gateway), fetch conversation, read `send_detailed_messages` from the gateway DB row (OFF → forward only AI; ON → forward AI/TOOL/INTERNAL), render, dispatch
- **Message rendering lives in the manager (CRITICAL)** - The manager converts `MessageContent` → `(text, image_file_keys)` (via `_render_message`) so the gateway stays dumb. Rules: AI → raw text; INTERNAL → `🔔 {text}`; TOOL with error → `❌ Tool {rendered_name}: error occured`; TOOL processing → `⚙️ Tool {rendered_name}`; TOOL done with images → images only (no text); TOOL done without images → nothing (skip). Tool-name rendering splits on the separator, uppercases all parts except the last, humanizes the last (underscores→spaces, capitalize first), joins with `-` (e.g. `ui__move_pointer` → `UI - Move pointer`)
- **User-message flow (manager owns it)** - `GatewayManager.handle_message(gateway_id, external_id, content, sender)`: find conversation via `database.conversations.get_by_gateway(gateway_id, external_id)`; if absent, read the gateway's `agent_id` from the DB and create a conversation bound to that agent with the gateway origin + sender; save the `MessageContentUser`; call `looper.process(conversation)`. The unique constraint `(gateway_id, gateway_external_id)` guarantees one conversation per chat
- **`_resolve_gateway` shared helper** - Resolves a conversation to `(instance, gateway_id, external_id)`: `gateway_id` None → skip (regular conversation); `external_id` None → `INVALID_RESPONSE` (malformed origin); not in `self.gateways` → `NOT_FOUND`. Used by both conversation-save and message-save handlers
- **Factory pattern** - GatewayBuilder creates gateway instances (routes on `config.type`), GatewayManagerBuilder creates the manager
- **Gateway folder structure** - Direct folders under `gateways/` (e.g., `gateways/telegram/`), no `implementations/` parent — mirrors bricks. Each platform gets its own folder so future gateways (WhatsApp, Discord) don't share a flat folder
- **Server-owned fields read/write boundary** - `Gateway.error_code`/`error_message` (gateway health) and `Conversation.gateway_id`/`gateway_external_id`/`sender` (gateway origin) are system-written, client-read: present in the proto READ message, absent from the proto INPUT message; the Python input DTO carries them so internal code (runtime/looper) can write them. Service `Save` preserves them on update by fetching the existing row (fetch-and-preserve)
- **Structural-identity immutability on update (CRITICAL)** - `GatewayStore.save` rejects changing `config.type` (`NOT_ALLOWED "Cannot change gateway config type"`) and `agent_id` (`NOT_ALLOWED "Cannot change gateway agent"`) on an existing gateway. The config TYPE follows the same rule as Provider/Brick/Preference stores (the type is intrinsic; changing it produces a meaningless row). The AGENT is gateway-specific: a conversation binds to the gateway's agent only at creation, so changing the agent would split-brain the gateway (existing chats keep the old agent, new chats get the new one). Editable on update: `name`, `send_detailed_messages`, error fields, and the config CONTENTS (token, allow_all, allowed_user_names). To switch a gateway's type or agent, delete and recreate it
- **Manager refresh triggers** - The server calls `gateway_manager.refresh()` (mirroring the `looper.refresh()` pattern) on: gateway Save/Delete (GatewaysService), agent Delete (AgentsService — agent delete CASCADE-deletes its gateways, so the manager must drop the orphaned instances and stop their loops), and preference SaveMany (PreferencesService — manager re-reads the tool-name separator). Agent _update_ does NOT trigger gateway refresh (gateway structure is unaffected)
- **Wired in AlentRed, parallel to the looper** - `GatewayManager` is constructed in `AlentRed.__init__` (synchronously, like Looper) so it exists for the Server constructor, `setup()` in `start()`, `clean()` in `stop()`. The looper NEVER imports gateways (gateways sit _outside_ the conversation loop — they feed user messages into it and observe it via buses) — this keeps `gateways → looper` one-directional with no cycle, so GatewayManager imports `Looper` plainly (no `TYPE_CHECKING`)

### Naming Conventions

**General Principles:**

- **Repository**: `alent-red-core` (kebab-case)
- **Package**: `alent_red_core` (snake_case)
- **Imports**: Relative imports preferred - `from .module import X`
- **Acronyms in names**: Use capitalized form, not all-caps (e.g., `Api` not `API`, `HttpUrl` not `HTTPURL`)

**Folder Naming:**

- **Singular** - Represents a concept or single logical unit
  - Examples: `database/`, `blob/`, `server/`, `common/`
- **Plural** - Holds multiple items of that type
  - Examples: `models/preferences/`, `server/services/`, `database/stores/`, `models/errors/`

**File Naming:**

- **Models** - Always singular, short naming
  - Examples: `preference.py` → `Preference`, `blob.py` → `Blob`, `error.py` → `Error`

- **Implementations**:
  - **When concept = implementation** (object itself) - Use short singular naming
    - Examples: `server.py` → `Server`, `database.py` → `Database`
  - **When model exists with same name** - Use suffix `_xxx` (preferred) or prefix `xxx_` (when more explicit)
    - Suffix pattern: `blob_storage.py` → `BlobStorage`, `preference_store.py` → `PreferenceStore`
    - Prefix pattern: `base_adapter.py` → `BaseAdapter` (for abstract base classes)
  - **Always singular** - Use singular form in all file names
  - **Exception**: gRPC service implementations must match proto service name exactly (singular or plural)

**Proto Naming:**

- **Proto files**: Always `messages.proto` + `services.proto` (both plural)
- **Proto packages**: `alent_red_core.{domain}` (e.g., `alent_red_core.info`)
- **Proto services**: Nouns without "Service" suffix (e.g., `service Info`, not `service InfoService`)

**Implementation File Naming:**

- **Python service files**: `{service}_service.py` (e.g., `info_service.py`, `preferences_service.py`)
- **Python service classes**: `{Service}Service` (e.g., `class InfoService(InfoServicer)`)
- **Store files**: `{domain}_store.py` (e.g., `preference_store.py`)
- **Store classes**: `{Domain}Store` (e.g., `class PreferenceStore`)

**Structure Examples:**

- **Database and Blob**: `database/` and `blob/` at package root (same level as server, models, etc.)
- **Stores**: `database/stores/{domain}_store.py`
- **Models**: `models/{domain}/` where domain is plural (e.g., `preferences/`, `providers/`)
- **Logger names**: Full package path (e.g., `server.services.preferences`, `blob`, `database.stores.preference_store`)

---

## Development Workflow

### Git Commit Messages

**Philosophy: Commit messages explain WHAT was done, not HOW**

- Detailed changes are visible in `git diff` - do not repeat them in commit message
- Keep commit messages short and high-level
- No bullet lists of file changes - that's what the diff is for

**Format:**

- **Subject line**: Short imperative summary, no trailing period
- **Body**: 1-2 sentences explaining what was accomplished (optional)
- **No credits**: Never add "Co-Authored-By" or similar

**Rules:**

- Subject: imperative mood (e.g., "Add feature", not "Added feature" or "Adds feature")
- No trailing period on subject line
- Body: high-level summary only, periods allowed
- NO bullet lists of specific changes (that's the diff's job)
- NO implementation details (that's the code's job)
- Short and sweet - anyone can read the diff for details

### Commands

```bash
./quick.sh setup           # First-time setup (installs uv, Python, deps, generates protos)
./quick.sh run             # Run the application
./quick.sh debug           # Run with debugger (waits for VSCode to attach on port 5678)
./quick.sh add main X      # Add production dependency
./quick.sh add dev X       # Add dev dependency
./quick.sh remove X        # Remove dependency
./quick.sh format          # Format code with Black (src/ and tests/)
./quick.sh typecheck       # Check types with mypy (src/ and tests/)
./quick.sh test [args...]  # Run pytest (preflight: tests/config.yml must exist; extra args pass through, e.g. -k pattern)
./quick.sh proto           # Generate Python code from proto files
./quick.sh build           # Compile standalone binary with Nuitka
./quick.sh release [--force] # Build + zip + upload the host platform asset to the GitHub release (--force overwrites after a 'yes' confirmation)
./quick.sh clean           # Clean everything (including .venv)
./quick.sh help            # Show all commands
./quick.sh                 # Interactive mode
```

### Cross-platform `quick.sh`

A single bash script supports macOS, Linux, and Windows (via Git Bash / MSYS2). The strategy:

- **`HOST_OS` detection** at the top of the script (`darwin` / `linux` / `windows` via MINGW/MSYS/CLANGARM64 uname patterns)
- **`SED_INPLACE` array** bridges the BSD vs GNU `sed` divide (`sed -i ''` on macOS vs `sed -i` on Linux/Git Bash). All in-place edits go through `"${SED_INPLACE[@]}"`
- **`ensure_uv_in_path()`** prepends `~/.local/bin` to PATH per-script-run if `uv(.exe)` lives there but the shell didn't pick it up (common on Windows after the Astral installer updates the user PATH in the registry but the current Git Bash session doesn't re-read it). **Never mutates the user's environment** — it only sets PATH for the current `./quick.sh` invocation
- **`install_uv`** branches by OS: PowerShell installer on Windows (`irm https://astral.sh/uv/install.ps1 | iex`), curl installer on Unix. After Windows install, prints (does not execute) the one-liner the user can run to make `uv` permanent in Git Bash
- **All Python invocations** use `uv run python` — never `python3`. Microsoft hijacks `python3` to a Microsoft Store popup on Windows
- **File writes through `>` redirect** use `.tmp` + `mv` (see "Bash `> redirect` truncates" under Cross-platform Quirks). Applied to encryption key generation in `ensure_dev_env`

**Windows requires Git for Windows** (provides Git Bash + MSYS2 toolchain). Git for Windows ARM64 (v2.47.1+) is fine — note its `uname.exe` is x86_64 (a packaging quirk), which makes Astral's installer download x86_64 `uv`, which downloads x86_64 Python — a coherent x86_64 chain end-to-end. This is what we want; see "Windows architecture (x86_64 only)" under Building.

### Proto Workflow

```bash
# 1. Edit .proto files in protos/
# 2. Generate Python code
./quick.sh proto

# Generated files go to: src/alent_red_core/generated/proto/
# - *_pb2.py (messages)
# - *_pb2_grpc.py (services)
# - *_pb2.pyi (type stubs)
#
# NOTE: Generated files are NOT committed to git
# They are regenerated automatically during setup
```

### Building (Nuitka standalone bundle)

`./quick.sh build` produces a self-contained binary bundle at `build/alent_red_core.dist/` that runs on the host OS+arch with no Python required at runtime.

**Single-platform output:** one build produces one binary for one (OS, arch). Multi-platform releases require running the build on each target host.

**macOS floor:** dictated by the Python interpreter's `MACOSX_DEPLOYMENT_TARGET`. uv-managed Python ships with `MACOSX_DEPLOYMENT_TARGET=11.0`, so binaries run on every Apple Silicon Mac.

**Nuitka flags and why** (static import analysis misses some lazy/data dependencies — every Python bundler has this problem):

- `--standalone` - Folder output. Code-signing friendly, no tmp-extraction at launch.
- `--python-flag=-m` + package directory (not `__main__.py`) - Preserves `__package__` so relative imports in `__main__.py` work.
- `--lto=yes` - Link-time optimization for end-user performance.
- `--include-package=...` for every runtime dep (anthropic, openai, pydantic, structlog, grpc, grpc_reflection, sqlalchemy.dialects.sqlite, aiosqlite) - Lazy submodule loading in SDKs is invisible to static analysis.
- `--include-package-data=alent_red_core.bricks.ui.assets` - Cursor PNGs loaded via `importlib.resources`.
- `--nofollow-import-to=mypy,mypyc,grpc_tools,pytest,_pytest,black,debugpy,ordered_set,zstandard` - Dev-only deps pulled in transitively (e.g., pydantic ships its own mypy plugin file that gets walked at build time even though it's never reached at runtime).
- `--macos-target-arch=$(uname -m)` (Darwin only) - Match host arch. Conditionally added in `cmd_build` so the script doesn't error on non-macOS hosts.

**Not used:**

- `--onefile` - Self-extractors complicate notarization and add an attack window.
- `--macos-create-app-bundle` - The consuming native app composes its own `.app`.
- Post-build `strip` - macOS wheels ship pre-stripped; running `strip` invalidates code signatures for zero benefit.

**Windows architecture (x86_64 only, including on ARM64 hosts):**

The shipped Windows binary is x86_64. On Windows ARM64 hardware (Snapdragon X, Surface Pro 11, Copilot+ PCs) it runs under Prism emulation. This is a deliberate choice, not a limitation we can fix today — every link in the chain is blocked:

- **`python-build-standalone`** (the project `uv` downloads Python from) **has no Windows ARM64 builds** as of 2026. `uv` on ARM64 transparently falls back to x86_64 Python
- **`grpcio`** has **no Windows ARM64 wheels on PyPI**. Building from source on Windows ARM64 is not supported by the gRPC project
- **Nuitka `--standalone`** does **not work** on Windows ARM64. Nuitka's documentation explicitly recommends Intel-based Python for standalone Windows builds

Windows ARM market share is small relative to x86_64, and Prism emulation is high-quality for I/O-bound workloads like alent-red-core (mostly gRPC + SQLite + HTTPS). The x86_64 binary runs natively on x86_64 hosts and emulated on ARM64 — same UX, marginal perf cost on ARM.

**When the ecosystem catches up** (Python ARM64 standalone + grpcio wheels + Nuitka `--standalone` fix on ARM), adding `windows-arm64` is a matter of running `./quick.sh build` on an ARM64 Windows host — no code changes needed.

### Releasing (GitHub Releases)

`./quick.sh release [--force]` builds, zips, and uploads the host platform's asset to the GitHub release of the current version.

**Version source of truth:** `__version__` in `src/alent_red_core/__init__.py`. `pyproject.toml` reads it via `dynamic = ["version"]` (hatchling). Runtime callers see it via `Info/GetInfo`. The release script greps it directly. To bump: edit that one line. No `version` command — version is a deliberate human decision.

**Release model:** one GitHub release per version, tagged `v{version}` (the tag is created by `gh release create` on the pushed HEAD, so the working tree must be clean and HEAD pushed to `origin`), with one asset per platform: `alent-red-core-{platform}.zip` plus a `.sha256` sidecar. The release is created by the first platform published and later platforms only add their asset. Never a draft (a draft has no public download URL). The repository is inferred from the `origin` remote by `gh`, so `quick.sh` holds no organization name or URL

**URL scheme:** `https://github.com/{owner}/alent-red-core/releases/download/v{version}/alent-red-core-{platform}.zip` where:

- `version` is PEP 440 format prefixed with `v` in tags only (e.g., `v0.1.0`). The version in `__init__.py` and PyPI metadata stays prefix-less (`0.1.0`)
- `platform` is `{os}-{arch}` (e.g., `macos-arm64`, `windows-x86_64`), from `detect_platform` (handles MINGW/MSYS/CLANGARM64 for Git Bash)
- The zip expands to a folder named `alent-red-core/` containing the binary + dylibs

**Release notes (CRITICAL):** `RELEASE_NOTES.md` at the repository root, one `## {version}` section per version, newest first. The release command reads ONLY the section of the current version and refuses to publish when it is missing or empty: writing the notes is part of releasing. Notes are set when the release is created (first platform) and never rewritten by later platforms. Keeping the file in git versions the whole history without depending on GitHub

**Version-collision policy:**

- Default: refuses to overwrite an asset already present on the release — bump the version instead
- `--force`: opt into overwrite (`gh release upload --clobber`), still requires interactive `yes` confirmation (not `y`, full word) before proceeding
- Probe happens BEFORE the build to avoid wasted compile time

**Preflight checks** (release fails fast if any missing):

- `gh` installed and authenticated (`gh auth status`)
- Version in `__init__.py` matches PEP 440 (`X.Y.Z` or `X.Y.Z[abrc]N`)
- Supported host OS+arch
- Release notes section present for the version
- Clean working tree and HEAD contained in a remote branch of `origin`
- After the build, no path under `$HOME` inside the bundle (see "CPython compiles its install prefix" under Cross-platform Quirks)

**Cross-platform:** the zip is produced with Python `shutil.make_archive` and the sha256 with `hashlib` so the command is identical on Windows Git Bash (no `zip`, no `shasum` there)

**No manifest, no `latest` alias:** consumer apps pin a specific version and verify the sha256 they were built against (the command prints both the URL and the sha256 to copy into the consumer's lockfile). External manifests would just be one more attacker-controllable surface.

### Testing

- **Framework** - `pytest` with `pytest-asyncio` in `asyncio_mode = "auto"` (every `async def test_*` runs in an event loop automatically; no `@pytest.mark.asyncio` decorator needed)
- **Test layout** - All tests live under `tests/`. End-to-end gRPC tests (spin up `AlentRed`, talk to it over a real channel) live under `tests/e2e/`. Future categories (e.g. `tests/unit/`) follow the same one-folder-per-category pattern
- **Test discovery (pytest defaults)** - File pattern `test_*.py`, class pattern `Test*`, function pattern `test_*`. Helpers inside test files are just regular un-prefixed functions/methods — pytest ignores them
- **Per-test isolation (CRITICAL)** - Each test gets its own `AlentRed` instance bound to a random free port, with its own SQLite DB and blob folder under pytest's `tmp_path`, and its own random AES-256 encryption key. No state shared between tests
- **Fixtures live in `tests/e2e/conftest.py`** - auto-discovered by pytest. Tests declare what they need by parameter name (no imports). Current fixtures:
  - `test_config` (session-scoped) — loads `tests/config.yml` once
  - `init_logger` (autouse) — initializes the global `Logger` before each test
  - `server` — boots `AlentRed` as a background task, waits for gRPC readiness via `channel_ready()`, yields the bound port, cleans up on teardown. Surfaces server startup crashes instead of swallowing them
  - `channel` — opens a gRPC `insecure_channel` to the test server's port
- **Test config** - `tests/config.yml` (gitignored) holds API keys and timeouts. `tests/config.example.yml` (committed) is the template. `./quick.sh test` fails fast if `tests/config.yml` is missing with instructions to copy the example
- **Test config schema (CRITICAL)** - `tests/e2e/config.py` defines Pydantic models (`TestConfig`, `ProvidersConfig`, `TimeoutsConfig`, etc.) that validate the YAML at load time. Missing/malformed keys fail loudly. Add new config sections by extending these models
- **Class-based organization** - Tests grouped in `Test{Service}` classes (e.g. `TestInfoService`). Class attributes can hold per-class constants like expected-value mappings; access via `self.CONSTANT_NAME`
- **Untyped generated stub calls** - The generated gRPC stubs (`services_pb2_grpc.XxxStub(channel)`) are intentionally untyped (`ignore_errors` for `alent_red_core.generated.*`). Calling them from a strict-typed test triggers mypy's `no-untyped-call`. Acceptable bypass: inline `# type: ignore[no-untyped-call]` at each stub construction line (per the mypy/black/strict-mode rule for explicit, agreed bypasses)
- **gRPC trailing-metadata type quirk** - `AioRpcError.trailing_metadata()` is typed by `grpc-stubs` as `tuple[_Metadatum, ...]` (a sync-RPC convention) but returns `grpc.aio.Metadata` at runtime. Tests cast to `Metadata` and use `.get(key)` to read the `error-code` / `error-message` entries
- **Test config file (`tests/config.yml`) must not be committed** - covered by a dedicated `.gitignore` entry; the `.example.yml` template stays committed

---

## Open Items & Known Constraints

These are areas that intentionally stop short today, with the reasoning preserved so contributors don't mistake them for bugs:

- **Bricks not yet implemented** - `CUSTOM` (path-based plugin loading), `RENDERER`, `BROWSER`, `AGENT` raise `NOT_SUPPORTED` in `BrickBuilder`. UI / CODE / SYSTEM / SCHEDULER / VISION / SKILLS are done
- **SkillsBrick scope** - Project-level roots (`.claude/skills`, `.agents/skills` in a repository), Claude Code plugins and the `synced/` folder are not scanned; no `create_skill` tool (the agent writes the folder with the System brick)
- **VisionBrick formats** - HEIC (iPhone / Photos) and SVG are refused with an explicit message; adding HEIC means the `pillow-heif` dependency plus a whitelist entry. PDF pages are out of scope (images only)
- **Gateways: only TELEGRAM** - WhatsApp/Discord/etc. are not implemented. Adding one is a new `GatewayConfig` variant + a new `gateways/{platform}/` folder + a `GatewayBuilder` branch
- **Tauri overlay (consumer side)** - The mouse-event passthrough mechanism requires native code on the Tauri side (Swift on macOS for geometric click-through, Win32 in Rust on Windows reading `dwExtraInfo` in `WndProc`). Core-side tagging is in place; overlay-side filtering is the consumer's work
- **`windows-arm64` native build** - Blocked by ecosystem (no Python ARM64 standalone, no grpcio ARM64 wheels, Nuitka `--standalone` broken on ARM). We ship x86_64 emulated via Prism. See "Windows architecture (x86_64 only)" under Building
- **`cmd_release` on Windows** - Written to run in Git Bash (Python zip + sha256, MINGW/MSYS/CLANGARM64 platform mapping) but not yet exercised there; to be verified at the first Windows release
- **MessageContentTool.error_message** - `Conversation` has split `error_code`/`error_message`; `MessageContentTool` still only has `error` (code). Tool errors lose text context when persisted, and adapters pass the bare enum value to the LLM as the tool result text
- **Telegram base URLs as constants** - The Bot API base URL and long-poll timeout are module constants in `TelegramClient`; to be promoted to preferences later (like OPEN_AI_BASE_URL / ANTHROPIC_BASE_URL)
- **Telegram large files** - `getFile` only serves files up to ~20MB (Bot API limit); larger attachments cannot be downloaded and are effectively skipped
- **Telegram sender refresh** - `ConversationSender` (name/user_name/picture) is written only when the conversation is CREATED, never updated on subsequent messages — so a returning user's renamed name/username does not propagate to an existing conversation. Picture is also fetched once per user per process lifetime (session-cached)
- **Telegram message dedup** - At-least-once delivery; a crash before the next offset bump redelivers the last batch. No `message_id`-based dedup (rare duplicates accepted)
- **Schema migration is additive-only** - `Database._ensure_schema` reconciles new tables / nullable columns / indexes automatically; renames, type changes, and NOT-NULL-without-default would need a manual ordered migration step (none exists today)
- **Streaming into the desktop** - partial saves arrive as `WatchSaves` updates on the same message id; the desktop must update in place and may show a typing indicator while `MessageContentAi.processing` is true
- **Streaming RPC error-handling dedup** - The four `Watch*` RPCs (on Conversations and Messages) each have an identical try/except/abort block. A stream-aware decorator analogous to `@handle_grpc_errors` is planned (decorators cannot wrap async generators directly)
- **gRPC mTLS support** - Planned for later
- **Encrypt sqlite file** - Planned for later
- **Provider rate limits** - Graceful handling (backoff, retry, surface to client) is planned
- **Token usage tracking** - Only the context size is tracked today (`Conversation.context_tokens_count`); cumulative cost per conversation or per message is not
- **Context compaction** - Automatically compact half of the conversation history when reaching a specific context window level
