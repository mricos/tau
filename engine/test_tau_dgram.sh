#!/usr/bin/env bash
# Test tau datagram communication

set -e

TAU_SOCKET="${TAU_SOCKET:-$HOME/tau/runtime/tau.sock}"

echo "=== TAU Datagram Communication Test ==="
echo "Socket: $TAU_SOCKET"
echo ""

# Helper function to send command
tau_send() {
    local cmd="$*"
    echo "→ $cmd"
    echo "$cmd" | socat - UNIX-DATAGRAM:$TAU_SOCKET 2>&1 | sed 's/^/← /'
    echo ""
}

# Check if tau is running
if ! pgrep -x "tau" > /dev/null; then
    echo "ERROR: tau not running!"
    echo "Start it with: ./tau"
    exit 1
fi

echo "✓ tau detected"
echo ""

# Wait for socket to be ready
sleep 1

if [ ! -S "$TAU_SOCKET" ]; then
    echo "ERROR: Socket not found: $TAU_SOCKET"
    exit 1
fi

echo "✓ Socket exists: $TAU_SOCKET"
echo ""

# Test commands
echo "--- Basic Commands ---"
tau_send "INIT"
tau_send "STATUS"

echo "--- Master Control ---"
tau_send "MASTER 0.5"
sleep 0.3
tau_send "MASTER 0.8"
sleep 0.3

echo "--- Channel Control ---"
tau_send "CH 1 GAIN 1.0"
tau_send "CH 1 PAN -0.5"
tau_send "CH 2 GAIN 1.0"
tau_send "CH 2 PAN 0.5"

echo "--- Voice Control ---"
tau_send "VOICE 1 WAVE 0"
tau_send "VOICE 1 FREQ 440.0"
tau_send "VOICE 1 GAIN 0.3"
tau_send "VOICE 1 CHAN 0"
tau_send "VOICE 1 ON"

echo "  (Playing 440Hz sine for 2 seconds...)"
sleep 2

tau_send "VOICE 1 OFF"

echo "--- Voice 2: Pulse Wave ---"
tau_send "VOICE 2 WAVE 1"
tau_send "VOICE 2 FREQ 220.0"
tau_send "VOICE 2 GAIN 0.25"
tau_send "VOICE 2 CHAN 1"
tau_send "VOICE 2 ON"

echo "  (Playing 220Hz pulse for 1 second...)"
sleep 1

tau_send "VOICE 2 OFF"

echo "--- Chord Test ---"
echo "  (Playing C major chord...)"
tau_send "VOICE 1 FREQ 261.63"
tau_send "VOICE 1 GAIN 0.2"
tau_send "VOICE 2 FREQ 329.63"
tau_send "VOICE 2 GAIN 0.2"
tau_send "VOICE 3 WAVE 0"
tau_send "VOICE 3 FREQ 392.00"
tau_send "VOICE 3 GAIN 0.2"
tau_send "VOICE 3 CHAN 2"

tau_send "VOICE 1 ON"
tau_send "VOICE 2 ON"
tau_send "VOICE 3 ON"

sleep 2

tau_send "VOICE 1 OFF"
tau_send "VOICE 2 OFF"
tau_send "VOICE 3 OFF"

echo "--- Sample Test ---"
# Check if we have a sample to test
SAMPLE_PATH="../tscale/audio.wav"
if [ -f "$SAMPLE_PATH" ]; then
    echo "  Found test sample: $SAMPLE_PATH"
    SAMPLE_FULL="$(cd "$(dirname "$SAMPLE_PATH")" && pwd)/$(basename "$SAMPLE_PATH")"

    tau_send "SAMPLE 1 LOAD $SAMPLE_FULL"
    tau_send "SAMPLE 1 GAIN 0.4"
    tau_send "SAMPLE 1 CHAN 3"
    tau_send "SAMPLE 1 TRIG"

    echo "  (Playing sample...)"
    sleep 2

    tau_send "SAMPLE 1 STOP"
else
    echo "  SKIPPED (no test sample found at $SAMPLE_PATH)"
fi

echo ""
echo "=== Test Complete ==="
echo ""
echo "To stop tau, send QUIT:"
echo "  echo 'QUIT' | socat - UNIX-DATAGRAM:$TAU_SOCKET"
