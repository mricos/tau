#!/usr/bin/env bash
# tau_recording.sh - Bash API for tau recording with lifecycle management
# Version: 1.0.0
# Requires: bash 5.2+, TAU_SRC environment variable

# Strict error handling
set -euo pipefail

# REQUIRES: TAU_SRC environment variable
if [[ ! -v TAU_SRC ]]; then
    echo "Error: TAU_SRC not set. Export TAU_SRC=/path/to/tau" >&2
    return 1
fi

# Python interpreter (can be overridden)
TAU_PYTHON="${TAU_PYTHON:-python3}"

# Runtime directory
TAU_RUNTIME="${TAU_RUNTIME:-$HOME/tau/runtime}"

#
# tau_start_recording <output_file> <t0_ns>
#
# Start tau-engine recording with auto-start.
# tau-engine will be launched if not already running.
#
# Args:
#   output_file: Output WAV path
#   t0_ns: Monotonic timestamp in nanoseconds
#
# Returns:
#   0 on success, non-zero on error
#
# Environment:
#   TAU_SRC: Path to tau source directory (required)
#   TAU_PYTHON: Python interpreter (default: python3)
#
tau_start_recording() {
    local output_file="$1"
    local t0_ns="$2"

    if [[ -z "$output_file" ]]; then
        echo "Error: output_file required" >&2
        return 1
    fi

    if [[ -z "$t0_ns" ]]; then
        echo "Error: t0_ns required" >&2
        return 1
    fi

    # Ensure output directory exists
    mkdir -p "$(dirname "$output_file")"

    # Ensure runtime directory exists
    mkdir -p "$TAU_RUNTIME"

    # Start recording using Python API
    # The TauRecorder class will auto-start tau-engine
    "$TAU_PYTHON" <<-EOF
import sys
sys.path.insert(0, '$TAU_SRC')
from pathlib import Path
from tau_lib.data.recording_api import TauRecorder

recorder = TauRecorder(auto_start=True)
try:
    recorder.start_recording(
        output_path=Path('$output_file'),
        t0_monotonic_ns=$t0_ns
    )
    print('✓ tau-engine recording started', file=sys.stderr)
    print('  Output: $output_file', file=sys.stderr)
    print('  T0: $t0_ns ns', file=sys.stderr)
except Exception as e:
    print(f'Error starting tau recording: {e}', file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
EOF

    return $?
}

#
# tau_stop_recording
#
# Stop tau-engine recording.
# Does NOT stop tau-engine daemon (in case other apps are using it).
#
# Returns:
#   0 on success, non-zero on error
#
tau_stop_recording() {
    "$TAU_PYTHON" <<-EOF
import sys
sys.path.insert(0, '$TAU_SRC')
from tau_lib.data.recording_api import TauRecorder

# Create recorder without auto-start (connect to existing)
recorder = TauRecorder(auto_start=False)

try:
    metadata = recorder.stop_recording()
    print('✓ tau-engine recording stopped', file=sys.stderr)
    print(f'  Duration: {metadata.get("duration_sec", 0):.3f} seconds', file=sys.stderr)
    print(f'  Frames: {metadata.get("frames_recorded", 0)}', file=sys.stderr)
except Exception as e:
    print(f'Error stopping tau recording: {e}', file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    sys.exit(1)
EOF

    return $?
}

#
# tau_cleanup_recording
#
# Stop recording AND stop tau-engine daemon.
# Use this when you're done with tau-engine entirely.
#
# Returns:
#   0 on success, non-zero on error
#
tau_cleanup_recording() {
    local result=0

    # First stop recording (if active)
    echo "Stopping tau recording..." >&2
    if ! tau_stop_recording 2>/dev/null; then
        echo "Note: No active recording to stop" >&2
    fi

    # Then stop tau-engine daemon
    echo "Stopping tau-engine daemon..." >&2
    "$TAU_PYTHON" <<-EOF 2>/dev/null || true
import sys
sys.path.insert(0, '$TAU_SRC')
from tau_lib.integration.tau_playback import TauMultitrack

tau = TauMultitrack(auto_start=False)
try:
    response = tau._send_command('QUIT')
    print('✓ tau-engine daemon stopped', file=sys.stderr)
except Exception as e:
    # Already stopped or not running
    pass
EOF

    # Wait a moment for graceful shutdown
    sleep 0.5

    # Kill any remaining tau-engine processes
    if pgrep -f tau-engine >/dev/null 2>&1; then
        echo "Forcefully terminating tau-engine..." >&2
        pkill -TERM -f tau-engine 2>/dev/null || true
        sleep 0.2
        pkill -KILL -f tau-engine 2>/dev/null || true
    fi

    # Verify cleanup
    if pgrep -f tau-engine >/dev/null 2>&1; then
        echo "Warning: tau-engine still running" >&2
        result=1
    else
        echo "✓ tau-engine cleanup complete" >&2
    fi

    return $result
}

#
# tau_recording_status
#
# Check if tau-engine is recording.
#
# Returns:
#   0 if recording, 1 if not recording or not running
#
# Output:
#   Human-readable status message
#
tau_recording_status() {
    "$TAU_PYTHON" <<-EOF
import sys
sys.path.insert(0, '$TAU_SRC')
from tau_lib.integration.tau_playback import TauMultitrack

tau = TauMultitrack(auto_start=False)
try:
    response = tau._send_command('RECORD STATUS')
    if 'RECORDING' in response and 'NOT_RECORDING' not in response:
        # Parse recording details
        print('Recording: Yes', file=sys.stderr)
        # Print response for details
        for line in response.split('\n'):
            if 'RECORDING' in line:
                print(f'  {line}', file=sys.stderr)
        sys.exit(0)
    else:
        print('Recording: No', file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print('Recording: No (tau-engine not running)', file=sys.stderr)
    sys.exit(1)
EOF
}

#
# tau_engine_status
#
# Check if tau-engine daemon is running.
#
# Returns:
#   0 if running, 1 if not
#
# Output:
#   Human-readable status message
#
tau_engine_status() {
    if pgrep -f tau-engine >/dev/null 2>&1; then
        local pid
        pid=$(pgrep -f tau-engine)
        echo "tau-engine: Running (PID: $pid)" >&2

        # Check socket
        local socket_path="$TAU_RUNTIME/tau.sock"
        if [[ -S "$socket_path" ]]; then
            echo "  Socket: $socket_path (active)" >&2
        else
            echo "  Socket: $socket_path (missing)" >&2
        fi

        return 0
    else
        echo "tau-engine: Not running" >&2
        return 1
    fi
}

#
# tau_ensure_stopped
#
# Ensure tau-engine is completely stopped.
# Idempotent - safe to call even if already stopped.
#
# Returns:
#   0 always
#
tau_ensure_stopped() {
    if pgrep -f tau-engine >/dev/null 2>&1; then
        echo "Ensuring tau-engine is stopped..." >&2
        tau_cleanup_recording
    else
        echo "tau-engine already stopped" >&2
    fi
    return 0
}

# Export functions for use in subshells
export -f tau_start_recording
export -f tau_stop_recording
export -f tau_cleanup_recording
export -f tau_recording_status
export -f tau_engine_status
export -f tau_ensure_stopped

# Module loaded successfully
[[ "${BASH_SOURCE[0]}" != "${0}" ]] && \
    echo "✓ tau_recording.sh loaded (functions: tau_start_recording, tau_stop_recording, tau_cleanup_recording, tau_recording_status)" >&2
