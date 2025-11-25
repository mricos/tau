#!/usr/bin/env bash
# test_tau_recording.sh - Test tau recording bash API
# Usage: ./test_tau_recording.sh

set -euo pipefail

# Setup
export TAU_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
echo "TAU_SRC=$TAU_SRC"

# Load API
source "$TAU_SRC/tau_lib/bash/tau_recording.sh"

# Test directory
TEST_DIR="/tmp/tau-recording-test"
mkdir -p "$TEST_DIR"

echo ""
echo "=== Test 1: Check tau-engine status (should be stopped) ==="
tau_engine_status || echo "✓ tau-engine not running (expected)"

echo ""
echo "=== Test 2: Start recording (should auto-start tau-engine) ==="
OUTPUT_FILE="$TEST_DIR/test_recording.wav"
T0_NS=$(python3 -c 'import time; print(int(time.monotonic_ns()))')
echo "T0: $T0_NS"

if tau_start_recording "$OUTPUT_FILE" "$T0_NS"; then
    echo "✓ Recording started"
else
    echo "✗ Failed to start recording"
    exit 1
fi

echo ""
echo "=== Test 3: Check tau-engine status (should be running) ==="
if tau_engine_status; then
    echo "✓ tau-engine is running"
else
    echo "✗ tau-engine should be running"
    exit 1
fi

echo ""
echo "=== Test 4: Check recording status ==="
if tau_recording_status; then
    echo "✓ Recording is active"
else
    echo "✗ Recording should be active"
    exit 1
fi

echo ""
echo "=== Test 5: Record for 3 seconds ==="
sleep 3

echo ""
echo "=== Test 6: Stop recording and cleanup tau-engine ==="
if tau_cleanup_recording; then
    echo "✓ Recording stopped and cleanup successful"
else
    echo "✗ Cleanup failed"
    exit 1
fi

echo ""
echo "=== Test 7: Check tau-engine status (should be stopped) ==="
tau_engine_status && {
    echo "✗ tau-engine should be stopped"
    exit 1
} || echo "✓ tau-engine stopped (expected)"

echo ""
echo "=== Test 8: Verify WAV file created ==="
if [[ -f "$OUTPUT_FILE" ]]; then
    FILE_SIZE=$(stat -f%z "$OUTPUT_FILE" 2>/dev/null || stat -c%s "$OUTPUT_FILE" 2>/dev/null)
    echo "✓ WAV file created: $OUTPUT_FILE"
    echo "  Size: $FILE_SIZE bytes"

    # Check with ffprobe if available
    if command -v ffprobe &>/dev/null; then
        echo ""
        echo "File info:"
        ffprobe "$OUTPUT_FILE" 2>&1 | grep -E "(Duration|Stream|Audio)" || true
    fi
else
    echo "✗ WAV file not created"
    exit 1
fi

echo ""
echo "=== Test 9: Check for orphaned processes ==="
if pgrep -f tau-engine >/dev/null; then
    echo "✗ Found orphaned tau-engine process:"
    pgrep -fl tau-engine
    exit 1
else
    echo "✓ No orphaned tau-engine processes"
fi

echo ""
echo "=== Test 10: Cleanup test files ==="
rm -rf "$TEST_DIR"
echo "✓ Test files cleaned up"

echo ""
echo "========================================="
echo "✅ All tests passed!"
echo "========================================="
echo ""
echo "Summary:"
echo "  - tau-engine auto-starts when recording begins"
echo "  - Recording works correctly"
echo "  - tau-engine stops when recording ends"
echo "  - No orphaned processes"
echo "  - Clean lifecycle management"
