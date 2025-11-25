#!/bin/bash
# Build tau standalone executable
#
# Usage:
#   ./build.sh        # Build for current platform
#   ./build.sh clean  # Clean build artifacts

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Detect platform
case "$(uname -s)" in
    Darwin*)  PLATFORM="macos" ;;
    Linux*)   PLATFORM="linux" ;;
    *)        PLATFORM="unknown" ;;
esac

echo "Building tau for $PLATFORM..."

# Clean
if [[ "$1" == "clean" ]]; then
    echo "Cleaning build artifacts..."
    rm -rf build/ dist/ *.egg-info
    rm -rf __pycache__ */__pycache__ */*/__pycache__
    echo "Done."
    exit 0
fi

# Build C engine first
echo "Building tau-engine..."
cd engine
./build.sh
cd ..

# Install Python dependencies
echo "Installing Python dependencies..."
pip install -e ".[dev]" --quiet

# Build standalone with PyInstaller
echo "Building standalone executable with PyInstaller..."
pyinstaller tau.spec --clean --noconfirm

# Verify
if [[ -f "dist/tau" ]]; then
    echo ""
    echo "Build successful!"
    echo "Executable: dist/tau"
    echo ""
    echo "Test with:"
    echo "  ./dist/tau --help"
    echo "  ./dist/tau tui"
else
    echo "Build failed!"
    exit 1
fi
