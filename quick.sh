#!/bin/bash

# Exit on error
set -e

# Get script directory and navigate to it
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Detect host OS once: "darwin", "linux", or "windows" (Git Bash / MSYS2 / Cygwin)
detect_os() {
    case "$(uname -s)" in
        Darwin)               echo "darwin" ;;
        Linux)                echo "linux" ;;
        MINGW*|MSYS*|CYGWIN*) echo "windows" ;;
        *)                    echo "unknown" ;;
    esac
}

HOST_OS=$(detect_os)

# sed -i syntax differs: BSD (macOS) requires '' after -i, GNU (Linux / Git Bash) does not
if [ "$HOST_OS" = "darwin" ]; then
    SED_INPLACE=("sed" "-i" "")
else
    SED_INPLACE=("sed" "-i")
fi

# Keep the uv-managed interpreter in a shared, user-independent location. CPython compiles
# its install prefix into libpython and sysconfig, and Nuitka embeds both in the bundle, so a
# per-user path (uv's default) would make the shipped binary depend on the build machine.
# only-managed keeps uv from picking an interpreter found on PATH instead.
case "$HOST_OS" in
    darwin)  export UV_PYTHON_INSTALL_DIR="/Users/Shared/uv/python" ;;
    windows) export UV_PYTHON_INSTALL_DIR="C:/ProgramData/uv/python" ;;
    *)       export UV_PYTHON_INSTALL_DIR="/opt/uv/python" ;;
esac
export UV_PYTHON_PREFERENCE="only-managed"

# Print info message (blue)
echo_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Print success message (green)
echo_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

# Print error message (red)
echo_error() {
    echo -e "${RED}❌ $1${NC}"
}

# Print warning message (yellow)
echo_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Print step message (blue)
echo_step() {
    echo -e "${BLUE}🔄 $1${NC}"
}

# Ensure ~/.local/bin is in PATH for this session if uv lives there.
# Astral's installer drops uv into ~/.local/bin but does not reliably
# update the user's shell PATH (especially on Windows). We extend PATH
# only for the current script execution — never touch the user's env.
ensure_uv_in_path() {
    if [ -x "$HOME/.local/bin/uv" ] || [ -x "$HOME/.local/bin/uv.exe" ]; then
        case ":$PATH:" in
            *":$HOME/.local/bin:"*) ;;
            *) export PATH="$HOME/.local/bin:$PATH" ;;
        esac
    fi
}

# Check if uv is installed
check_uv() {
    ensure_uv_in_path
    if command -v uv &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# Install uv if not found
install_uv() {
    echo_step "Installing uv..."

    if [ "$HOST_OS" = "windows" ]; then
        # Astral's official Windows installer runs in PowerShell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        # The PS installer updates the user PATH in the Windows registry,
        # but this Git Bash session won't pick it up until restart. Add
        # the known install locations to PATH for the current session so
        # check_uv succeeds immediately. Subsequent Git Bash sessions
        # will see uv naturally via the registry-updated PATH.
        export PATH="$USERPROFILE/.local/bin:$LOCALAPPDATA/Programs/uv:$PATH"
    else
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    fi

    # Verify installation
    if check_uv; then
        echo_success "uv installed successfully!"

        # On Windows, the installer does not reliably wire uv into Git
        # Bash's PATH. quick.sh extends PATH per-run via ensure_uv_in_path,
        # but `uv` typed directly in Git Bash won't work until the user
        # adds it themselves. Surface the one-liner; don't touch their env.
        if [ "$HOST_OS" = "windows" ]; then
            echo ""
            echo_warning "To run 'uv' directly in Git Bash (outside ./quick.sh),"
            echo_warning "add it to your PATH permanently by running:"
            echo ""
            echo "  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc"
            echo ""
            echo_info "Then close and reopen Git Bash. (Optional — ./quick.sh works without it.)"
        fi
    else
        echo_error "uv installation failed. Please install manually:"
        echo_info "Visit: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
}

# Setup command: Install uv and project dependencies
cmd_setup() {
    echo_info "Starting project setup..."
    echo ""

    # Check if uv is installed, install if missing
    if ! check_uv; then
        echo_warning "uv not found!"
        install_uv
    else
        echo_success "uv is already installed"
    fi

    echo ""
    echo_step "Installing project dependencies (Python 3.10 + venv + deps)..."
    # uv sync auto-installs the required Python, creates .venv/, installs all deps from uv.lock
    uv sync

    echo ""
    echo_step "Generating proto files..."
    cmd_proto

    echo ""
    echo_success "Setup complete! 🎉"
    echo ""
}

# Ensure dev environment is ready (dirs + encryption key)
ensure_dev_env() {
    mkdir -p "$SCRIPT_DIR/dev/blob"

    # -s checks "exists AND non-empty". A previous failed generation may
    # have left an empty file behind because `command > file` truncates
    # the destination BEFORE running the command (POSIX bash behavior on
    # every OS). Writing through a temp file + atomic mv guarantees the
    # final file is either valid or absent.
    if [ ! -s "$SCRIPT_DIR/dev/encryption_key.txt" ]; then
        echo_step "Generating encryption key..."
        local key_path="$SCRIPT_DIR/dev/encryption_key.txt"
        local tmp_path="$key_path.tmp"
        uv run python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())" > "$tmp_path"
        mv "$tmp_path" "$key_path"
        echo_success "Encryption key generated at dev/encryption_key.txt"
    fi
}

# Run command: Start the application
cmd_run() {
    # Check if virtual environment exists
    if [ ! -d ".venv" ]; then
        echo_error "Virtual environment not found!"
        echo_info "Run './quick.sh setup' first"
        exit 1
    fi

    ensure_dev_env

    echo_info "Starting ALENT.RED Core..."
    echo ""

    ENCRYPTION_KEY=$(cat "$SCRIPT_DIR/dev/encryption_key.txt")

    uv run python -m alent_red_core \
        --host "127.0.0.1" \
        --port 50051 \
        --sqlite-path "$SCRIPT_DIR/dev/database.db" \
        --blob-path "$SCRIPT_DIR/dev/blob" \
        --encryption-key "$ENCRYPTION_KEY" \
        --log-level "DEBUG"
}

# Debug command: Start the application with debugger
cmd_debug() {
    # Check if virtual environment exists
    if [ ! -d ".venv" ]; then
        echo_error "Virtual environment not found!"
        echo_info "Run './quick.sh setup' first"
        exit 1
    fi

    ensure_dev_env

    echo_info "Starting ALENT.RED Core in debug mode..."
    echo_warning "Waiting for debugger to attach on port 5678..."
    echo_info "In VSCode debug panel: Select 'Attach to Debug' and start debugging"
    echo ""

    ENCRYPTION_KEY=$(cat "$SCRIPT_DIR/dev/encryption_key.txt")

    uv run python -m debugpy --listen 5678 --wait-for-client -m alent_red_core \
        --host "127.0.0.1" \
        --port 50051 \
        --sqlite-path "$SCRIPT_DIR/dev/database.db" \
        --blob-path "$SCRIPT_DIR/dev/blob" \
        --encryption-key "$ENCRYPTION_KEY" \
        --log-level "DEBUG"
}

# Add command: Add dependencies (main or dev)
cmd_add() {
    local dep_type="$1"
    shift
    local packages="$@"

    # Validate dependency type
    if [[ "$dep_type" != "main" && "$dep_type" != "dev" ]]; then
        echo_error "Invalid dependency type: $dep_type"
        echo_info "Usage: ./quick.sh add [main|dev] package1 package2 ..."
        exit 1
    fi

    # Check if packages provided
    if [ -z "$packages" ]; then
        echo_error "No packages specified!"
        echo_info "Usage: ./quick.sh add [main|dev] package1 package2 ..."
        exit 1
    fi

    echo_info "Adding $dep_type dependencies: $packages"
    echo ""

    # Add dependencies based on type
    if [ "$dep_type" = "main" ]; then
        echo_step "Adding to main dependencies..."
        uv add $packages
    else
        echo_step "Adding to dev dependencies..."
        uv add --dev $packages
    fi

    echo ""
    echo_success "Dependencies added successfully! 🎉"
    echo ""
}

# Remove command: Remove dependencies
cmd_remove() {
    local packages="$@"

    # Check if packages provided
    if [ -z "$packages" ]; then
        echo_error "No packages specified!"
        echo_info "Usage: ./quick.sh remove package1 package2 ..."
        exit 1
    fi

    echo_info "Removing dependencies: $packages"
    echo ""

    echo_step "Removing packages..."
    uv remove $packages

    echo ""
    echo_success "Dependencies removed successfully! 🎉"
    echo ""
}

# Proto command: Generate Python code from proto files
cmd_proto() {
    echo_info "Generating Python code from proto files..."
    echo ""

    # Check if protos directory exists
    if [ ! -d "protos" ]; then
        echo_error "protos/ directory not found!"
        exit 1
    fi

    # Create output directory if it doesn't exist
    mkdir -p src/alent_red_core/generated/proto

    echo_step "Compiling proto files..."
    uv run python -m grpc_tools.protoc \
        --proto_path=protos \
        --python_out=src/alent_red_core/generated/proto \
        --grpc_python_out=src/alent_red_core/generated/proto \
        --pyi_out=src/alent_red_core/generated/proto \
        $(find protos -name "*.proto")

    # protoc generates absolute imports by default, but our package structure requires relative imports
    echo_step "Fixing imports in generated files..."
    find src/alent_red_core/generated/proto -name "*_pb2_grpc.py" -o -name "*_pb2.py" | while read file; do
        # Fix cross-domain imports first (e.g., common/errors.proto imported from conversations/)
        # from common import errors_pb2 -> from ..common import errors_pb2
        "${SED_INPLACE[@]}" 's/^from common import \([a-z_]*\)_pb2/from ..common import \1_pb2/' "$file"

        # Fix imports like: from server import messages_pb2
        # to: from . import messages_pb2
        "${SED_INPLACE[@]}" 's/^from \([a-z_]*\) import \([a-z_]*\)_pb2/from . import \2_pb2/' "$file"

        # Fix imports like: import messages_pb2
        # to: from . import messages_pb2
        "${SED_INPLACE[@]}" 's/^import \([a-z_]*\)_pb2 as \(.*\)$/from . import \1_pb2 as \2/' "$file"
    done

    echo ""
    echo_success "Proto files compiled successfully! 🎉"
    echo ""
}

# Format command: Format code with Black
cmd_format() {
    echo_info "Formatting code with Black..."
    echo ""

    echo_step "Running Black formatter..."
    uv run black src/ tests/

    echo ""
    echo_success "Code formatted successfully! 🎨"
    echo ""
}

# Typecheck command: Check types with mypy
cmd_typecheck() {
    echo_info "Type checking with mypy..."
    echo ""

    echo_step "Running mypy type checker..."
    uv run mypy src/ tests/

    echo ""
    echo_success "Type checking complete! ✅"
    echo ""
}

# Test command: Run pytest (passes any extra args through to pytest)
cmd_test() {
    if [ ! -f "$SCRIPT_DIR/tests/config.yml" ]; then
        echo_error "Missing tests/config.yml"
        echo_info "Copy tests/config.example.yml to tests/config.yml and fill in your API keys:"
        echo_info "  cp tests/config.example.yml tests/config.yml"
        exit 1
    fi

    echo_info "Running tests..."
    echo ""

    uv run pytest "$@"

    echo ""
    echo_success "Tests complete! ✅"
    echo ""
}

# Build command: Compile standalone binary with Nuitka
cmd_build() {
    # Check if virtual environment exists
    if [ ! -d ".venv" ]; then
        echo_error "Virtual environment not found!"
        echo_info "Run './quick.sh setup' first"
        exit 1
    fi

    echo_info "Building standalone binary with Nuitka..."
    echo ""

    # Ensure proto files exist before building
    if [ ! -d "src/alent_red_core/generated/proto" ]; then
        echo_step "Generating proto files..."
        cmd_proto
    fi

    # Remove previous build to avoid stale artifacts
    echo_step "Cleaning previous build..."
    rm -rf build/

    # Detect host OS+arch and build platform-specific Nuitka flags
    HOST_OS=$(uname -s)
    HOST_ARCH=$(uname -m)
    PLATFORM_FLAGS=()
    if [ "$HOST_OS" = "Darwin" ]; then
        PLATFORM_FLAGS+=("--macos-target-arch=$HOST_ARCH")
    fi
    echo_info "Building for $HOST_OS $HOST_ARCH"
    echo ""

    echo_step "Running Nuitka (this takes several minutes on first build)..."
    uv run python -m nuitka \
        --standalone \
        --python-flag=-m \
        --lto=yes \
        --output-dir=build \
        --output-filename=alent-red-core \
        --output-folder-name=alent-red-core \
        --include-package=alent_red_core \
        --include-package=alent_red_core.generated \
        --include-package-data=alent_red_core.bricks.ui.assets \
        --include-package=grpc \
        --include-package=grpc_reflection \
        --include-package=sqlalchemy.dialects.sqlite \
        --include-package=aiosqlite \
        --include-package=anthropic \
        --include-package=openai \
        --include-package=pydantic \
        --include-package=structlog \
        --include-package=yaml \
        --include-package=httpx \
        --nofollow-import-to=mypy \
        --nofollow-import-to=mypyc \
        --nofollow-import-to=grpc_tools \
        --nofollow-import-to=pytest \
        --nofollow-import-to=_pytest \
        --nofollow-import-to=black \
        --nofollow-import-to=debugpy \
        --nofollow-import-to=ordered_set \
        --nofollow-import-to=zstandard \
        "${PLATFORM_FLAGS[@]}" \
        --assume-yes-for-downloads \
        --remove-output \
        src/alent_red_core

    # Nuitka hardcodes a .dist suffix on the output folder; rename to drop it
    rm -rf build/alent-red-core
    mv build/alent-red-core.dist build/alent-red-core

    BUNDLE_DIR="build/alent-red-core"
    BUNDLE_SIZE=$(du -sh "$BUNDLE_DIR" | cut -f1)

    echo ""
    echo_success "Build complete! 🎉"
    echo_info "Bundle: $BUNDLE_DIR ($BUNDLE_SIZE)"
    echo_info "Binary: $BUNDLE_DIR/alent-red-core"
    echo ""
}

# Read __version__ from src/alent_red_core/__init__.py (single source of truth)
read_version() {
    grep '^__version__' src/alent_red_core/__init__.py | sed -E 's/^__version__[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/'
}

# Map host OS+arch to the release platform string (e.g. "macos-arm64")
detect_platform() {
    local os
    local arch
    os=$(uname -s)
    arch=$(uname -m)

    case "$os" in
        Darwin)                           os="macos" ;;
        Linux)                            os="linux" ;;
        MINGW*|MSYS*|CLANGARM64*|CYGWIN*) os="windows" ;;
        *)                                echo_error "Unsupported OS: $os" >&2; return 1 ;;
    esac

    case "$arch" in
        arm64|aarch64) arch="arm64" ;;
        x86_64|amd64)  arch="x86_64" ;;
        *)             echo_error "Unsupported arch: $arch" >&2; return 1 ;;
    esac

    echo "${os}-${arch}"
}

# Extract the "## <version>" section of RELEASE_NOTES.md (up to the next "## " heading)
read_release_notes() {
    local version="$1"
    awk -v version="$version" '
        /^## / { in_section = ($2 == version); next }
        in_section { print }
    ' RELEASE_NOTES.md | sed -e '/./,$!d' | sed -e ':a' -e '/^\n*$/{$d;N;ba' -e '}'
}

# Release command: Build + zip + upload one platform asset to the GitHub release of the current version
cmd_release() {
    local force=false
    if [ "$1" = "--force" ]; then
        force=true
    elif [ -n "$1" ]; then
        echo_error "Unknown argument: $1"
        echo_info "Usage: ./quick.sh release [--force]"
        exit 1
    fi

    # Version from the single source of truth
    local version
    version=$(read_version)
    if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+([a-z]+[0-9]+)?$ ]]; then
        echo_error "Invalid or unreadable version: '$version'"
        echo_info "Expected PEP 440 format like '0.1.0' or '0.1.0a1' in src/alent_red_core/__init__.py"
        exit 1
    fi

    local platform
    platform=$(detect_platform) || exit 1

    local tag="v${version}"
    local asset_name="alent-red-core-${platform}.zip"

    echo_info "Version:  $version"
    echo_info "Platform: $platform"
    echo_info "Tag:      $tag"
    echo ""

    # Preflight: gh installed and authenticated
    if ! command -v gh &> /dev/null; then
        echo_error "GitHub CLI (gh) not installed."
        echo_info "Install: https://cli.github.com/"
        exit 1
    fi
    if ! gh auth status &> /dev/null; then
        echo_error "GitHub CLI not authenticated."
        echo_info "Run: gh auth login"
        exit 1
    fi

    # Preflight: release notes written for this version
    local notes
    notes=$(read_release_notes "$version")
    if [ -z "$notes" ]; then
        echo_error "No release notes for $version in RELEASE_NOTES.md"
        echo_info "Add a '## $version' section with the changes before releasing."
        exit 1
    fi

    # Preflight: the tag is created on HEAD, so HEAD must be committed and pushed
    if [ -n "$(git status --porcelain)" ]; then
        echo_error "Working tree is not clean. Commit or stash before releasing."
        exit 1
    fi
    git fetch --quiet origin
    if [ -z "$(git branch --remotes --contains HEAD)" ]; then
        echo_error "HEAD is not pushed to origin. Push before releasing."
        exit 1
    fi

    # Probe: release and asset existence
    local release_exists=false
    local existing_assets=""
    if existing_assets=$(gh release view "$tag" --json assets --jq '.assets[].name' 2>/dev/null); then
        release_exists=true
    fi

    if [ "$release_exists" = true ] && echo "$existing_assets" | grep -qx "$asset_name"; then
        if [ "$force" = false ]; then
            echo_error "Asset $asset_name already published on release $tag."
            echo_info "Bump __version__ in src/alent_red_core/__init__.py, or pass --force to overwrite."
            exit 1
        fi

        echo_warning "Asset $asset_name already published on release $tag."
        echo_warning "This will OVERWRITE the existing asset."
        read -p "Type 'yes' to confirm: " confirmation
        if [ "$confirmation" != "yes" ]; then
            echo_error "Aborted (no 'yes' confirmation)."
            exit 1
        fi
    elif [ "$release_exists" = true ]; then
        echo_success "Release $tag exists, $asset_name will be added."
    else
        echo_success "Release $tag does not exist yet, it will be created."
    fi
    echo ""

    # Build fresh (always)
    cmd_build

    # Hermeticity: the bundle must not embed build-machine paths. On Windows the home
    # folder can appear as C:\Users\name or C:/Users/name, never as Git Bash's /c/Users/name.
    echo_step "Checking the bundle for build-machine paths..."
    local home_patterns=("-e" "$HOME")
    if [ "$HOST_OS" = "windows" ] && [ -n "$USERPROFILE" ]; then
        home_patterns+=("-e" "$USERPROFILE" "-e" "${USERPROFILE//\\//}")
    fi
    local tainted_files
    tainted_files=$(grep -rl -a -F "${home_patterns[@]}" "$BUNDLE_DIR" || true)
    if [ -n "$tainted_files" ]; then
        echo_error "The bundle embeds paths under $HOME:"
        echo "$tainted_files"
        echo_info "Run './quick.sh clean' then './quick.sh setup' so the interpreter is reinstalled under $UV_PYTHON_INSTALL_DIR, and build again."
        exit 1
    fi
    echo_success "No build-machine path in the bundle."
    echo ""

    # Zip the bundle. Python's shutil.make_archive keeps the command identical on
    # Windows Git Bash (no `zip` there). make_archive("name", "zip", root_dir, base_dir)
    # produces name.zip whose entries are rooted at base_dir inside root_dir.
    local release_dir="build/release"
    local zip_path="$release_dir/$asset_name"
    mkdir -p "$release_dir"
    rm -f "$zip_path"

    echo_step "Zipping $BUNDLE_DIR..."
    uv run python -c "import shutil, sys; shutil.make_archive(sys.argv[1], 'zip', sys.argv[2], sys.argv[3])" \
        "$release_dir/alent-red-core-${platform}" "build" "alent-red-core"
    local zip_size
    zip_size=$(du -sh "$zip_path" | cut -f1)
    echo_success "Zipped: $zip_path ($zip_size)"

    # sha256 through Python as well (no `shasum` on Windows Git Bash)
    local sha
    sha=$(uv run python -c "import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())" "$zip_path")
    local sha_path="${zip_path}.sha256"
    echo "$sha  $asset_name" > "$sha_path"
    echo ""

    # Create the release on first platform, with the notes of this version only
    if [ "$release_exists" = false ]; then
        local notes_path="$release_dir/notes.md"
        printf '%s\n' "$notes" > "$notes_path"
        echo_step "Creating release $tag..."
        gh release create "$tag" --title "$tag" --notes-file "$notes_path"
        echo_success "Release created."
    fi

    # Upload the platform assets
    local upload_flags=()
    if [ "$force" = true ]; then
        upload_flags+=("--clobber")
    fi
    echo_step "Uploading $asset_name..."
    gh release upload "$tag" "$zip_path" "$sha_path" "${upload_flags[@]}"
    echo_success "Upload complete."
    echo ""

    # Report
    local repository
    repository=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
    echo_success "Released $version / $platform 🚀"
    echo_info "URL:    https://github.com/${repository}/releases/download/${tag}/${asset_name}"
    echo_info "sha256: $sha"
    echo ""
}

# Clean command: Remove all generated files and venv
cmd_clean() {
    echo_info "Cleaning project..."
    echo ""

    # Remove Python cache directories and files
    echo_step "Removing Python cache files..."
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    find . -type f -name "*.pyo" -delete 2>/dev/null || true
    echo_success "Python cache cleaned"

    # Remove test-related artifacts
    echo_step "Removing test artifacts..."
    rm -rf .pytest_cache 2>/dev/null || true
    rm -rf .coverage htmlcov 2>/dev/null || true
    echo_success "Test artifacts cleaned"

    # Remove mypy cache
    echo_step "Removing mypy cache..."
    rm -rf .mypy_cache 2>/dev/null || true
    echo_success "Mypy cache cleaned"

    # Remove build and distribution artifacts
    echo_step "Removing build artifacts..."
    rm -rf build dist 2>/dev/null || true
    find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
    echo_success "Build artifacts cleaned"

    # Remove virtual environment
    echo_step "Removing virtual environment..."
    rm -rf .venv 2>/dev/null || true
    echo_success "Virtual environment removed"

    echo ""
    echo_success "Cleanup complete! 🧹"
    echo_info "Run './quick.sh setup' to reinstall everything"
    echo ""
}

# Display help message with all available commands
cmd_help() {
    echo ""
    echo -e "${GREEN}🚀 ALENT.RED Core - Quick Commands${NC}"
    echo ""
    echo "Usage: ./quick.sh [command]"
    echo ""
    echo "Commands:"
    echo "  setup              - First-time project setup (install uv, Python, dependencies)"
    echo "  run                - Run the application"
    echo "  debug              - Run the application with debugger (attach from VSCode)"
    echo "  add [main|dev] ... - Add dependencies (main or dev)"
    echo "  remove ...         - Remove dependencies"
    echo "  format             - Format code with Black"
    echo "  typecheck          - Check types with mypy"
    echo "  test [args...]     - Run pytest (extra args passed through, e.g. -k pattern)"
    echo "  proto              - Generate Python code from proto files"
    echo "  build              - Compile standalone binary with Nuitka"
    echo "  release [--force]  - Build + zip + upload to the GitHub release of the current version (--force overwrites an existing asset after a 'yes' confirmation)"
    echo "  clean              - Clean build artifacts and virtual environment"
    echo "  help               - Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./quick.sh proto"
    echo "  ./quick.sh format"
    echo "  ./quick.sh typecheck"
    echo "  ./quick.sh test"
    echo "  ./quick.sh test -k provider"
    echo "  ./quick.sh test tests/e2e/test_info_service.py"
    echo "  ./quick.sh build"
    echo "  ./quick.sh release"
    echo "  ./quick.sh add main grpcio protobuf"
    echo "  ./quick.sh add dev pytest black ruff"
    echo "  ./quick.sh remove grpcio"
    echo ""
    echo "If no command is provided, interactive mode will start."
    echo ""
}

# Display interactive menu
show_menu() {
    echo ""
    echo -e "${GREEN}🚀 ALENT.RED Core - Quick Commands${NC}"
    echo ""
    echo "1. setup      - First-time project setup"
    echo "2. run        - Run the application"
    echo "3. debug      - Run with debugger (attach from VSCode)"
    echo "4. add        - Add dependencies"
    echo "5. remove     - Remove dependencies"
    echo "6. format     - Format code with Black"
    echo "7. typecheck  - Check types with mypy"
    echo "8. test       - Run tests with pytest"
    echo "9. proto      - Generate Python code from proto files"
    echo "10. build     - Compile standalone binary with Nuitka"
    echo "11. release   - Build + zip + upload to GitHub Releases"
    echo "12. clean     - Clean build artifacts and venv"
    echo "13. exit      - Exit"
    echo ""
}

# Interactive mode: Show menu and handle user input
interactive_mode() {
    while true; do
        show_menu
        read -p "Select option (1-13): " choice
        echo ""

        case $choice in
            1)
                cmd_setup
                ;;
            2)
                cmd_run
                ;;
            3)
                cmd_debug
                ;;
            4)
                # Add dependencies interactively
                echo "Dependency type:"
                echo "  1. Main (production)"
                echo "  2. Dev (development)"
                read -p "Select type (1-2): " dep_choice
                echo ""

                if [ "$dep_choice" = "1" ]; then
                    dep_type="main"
                elif [ "$dep_choice" = "2" ]; then
                    dep_type="dev"
                else
                    echo_error "Invalid choice!"
                    continue
                fi

                read -p "Enter package names (space-separated): " packages
                if [ -n "$packages" ]; then
                    cmd_add "$dep_type" $packages
                else
                    echo_error "No packages specified!"
                fi
                ;;
            5)
                # Remove dependencies interactively
                read -p "Enter package names to remove (space-separated): " packages
                if [ -n "$packages" ]; then
                    cmd_remove $packages
                else
                    echo_error "No packages specified!"
                fi
                ;;
            6)
                cmd_format
                ;;
            7)
                cmd_typecheck
                ;;
            8)
                cmd_test
                ;;
            9)
                cmd_proto
                ;;
            10)
                cmd_build
                ;;
            11)
                cmd_release
                ;;
            12)
                cmd_clean
                ;;
            13)
                echo_info "Goodbye! 👋"
                exit 0
                ;;
            *)
                echo_error "Invalid option. Please select 1-13."
                ;;
        esac

        echo ""
        read -p "Press Enter to continue..."
    done
}

# Main entry point
# If no arguments, start interactive mode
# Otherwise, execute the specified command

# Extend PATH for this script's session if uv lives in ~/.local/bin but
# the user's shell hasn't picked it up (common on Windows after the
# Astral installer). Per-run only; never mutates the user's environment.
ensure_uv_in_path

if [ $# -eq 0 ]; then
    interactive_mode
else
    case "$1" in
        setup)
            cmd_setup
            ;;
        run)
            cmd_run
            ;;
        debug)
            cmd_debug
            ;;
        add)
            shift
            cmd_add "$@"
            ;;
        remove)
            shift
            cmd_remove "$@"
            ;;
        format)
            cmd_format
            ;;
        typecheck)
            cmd_typecheck
            ;;
        test)
            shift
            cmd_test "$@"
            ;;
        proto)
            cmd_proto
            ;;
        build)
            cmd_build
            ;;
        release)
            shift
            cmd_release "$@"
            ;;
        clean)
            cmd_clean
            ;;
        help|--help|-h)
            cmd_help
            ;;
        *)
            echo_error "Unknown command: $1"
            cmd_help
            exit 1
            ;;
    esac
fi
