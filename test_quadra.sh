#!/usr/bin/env bash
# test_quadra.sh - Test script for Quadra audio engine
# Demonstrates OSC control of synthesis, samples, and mixing

set -e

OSC_PORT=9001
OSC_HOST="localhost"

# Helper function to send OSC messages
osc() {
    oscsend "$OSC_HOST" "$OSC_PORT" "$@"
}

echo "=== Quadra Audio Engine Test Script ==="
echo "OSC Target: $OSC_HOST:$OSC_PORT"
echo ""

# Check if engine is running
if ! pgrep -x "engine" > /dev/null; then
    echo "ERROR: Quadra engine not running!"
    echo "Start it with: ./engine --config quadra.json"
    exit 1
fi

echo "✓ Engine detected"
echo ""

# =============================================================================
# BASIC OSC COMMANDS
# =============================================================================

echo "--- Master Controls ---"
echo "Setting master gain to 0.5"
osc /master/gain f 0.5
sleep 0.5

echo "Setting master gain back to 0.8"
osc /master/gain f 0.8
sleep 0.5
echo ""

# =============================================================================
# MIXER CHANNELS (1-4)
# =============================================================================

echo "--- Channel Controls ---"
echo "Channel 1: gain=1.0, pan=-0.8 (left)"
osc /ch/1/gain f 1.0
osc /ch/1/pan f -0.8
sleep 0.3

echo "Channel 2: gain=1.0, pan=0.8 (right)"
osc /ch/2/gain f 1.0
osc /ch/2/pan f 0.8
sleep 0.3

echo "Channel 3: gain=0.7, pan=0.0 (center), lowpass filter @ 800Hz"
osc /ch/3/gain f 0.7
osc /ch/3/pan f 0.0
osc /ch/3/filter i 1 f 800.0 f 1.0
sleep 0.3
echo ""

# =============================================================================
# SYNTH VOICES (1-8)
# =============================================================================

echo "--- Synth Voice Tests ---"

echo "Test 1: Simple sine wave (220 Hz, channel 1)"
osc /synth/1/wave i 0          # 0=sine
osc /synth/1/freq f 220.0      # A3
osc /synth/1/gain f 0.3
osc /synth/1/chan i 0          # channel 1 (0-indexed)
osc /synth/1/on i 1            # turn on
sleep 1.5
osc /synth/1/on i 0            # turn off
echo ""

echo "Test 2: Pulse wave with LIF modulation (440 Hz, channel 2)"
osc /synth/2/wave i 1          # 1=pulse
osc /synth/2/freq f 440.0      # A4
osc /synth/2/gain f 0.25
osc /synth/2/chan i 1          # channel 2
osc /synth/2/tau f 0.005 f 0.02  # tau_a, tau_b (LIF time constants)
osc /synth/2/duty f 0.5        # base duty cycle
osc /synth/2/on i 1
sleep 0.5

echo "  Injecting 3 spikes to modulate pulse width..."
osc /synth/2/spike             # spike 1
sleep 0.2
osc /synth/2/spike             # spike 2
sleep 0.2
osc /synth/2/spike             # spike 3
sleep 1.0
osc /synth/2/on i 0
echo ""

echo "Test 3: Chord (3 voices, channels 1-3)"
# Voice 1: C4 (261.63 Hz)
osc /synth/1/wave i 0
osc /synth/1/freq f 261.63
osc /synth/1/gain f 0.2
osc /synth/1/chan i 0
osc /synth/1/on i 1

# Voice 2: E4 (329.63 Hz)
osc /synth/2/wave i 0
osc /synth/2/freq f 329.63
osc /synth/2/gain f 0.2
osc /synth/2/chan i 1
osc /synth/2/on i 1

# Voice 3: G4 (392.00 Hz)
osc /synth/3/wave i 0
osc /synth/3/freq f 392.00
osc /synth/3/gain f 0.2
osc /synth/3/chan i 2
osc /synth/3/on i 1

sleep 2.0

# Turn off chord
osc /synth/1/on i 0
osc /synth/2/on i 0
osc /synth/3/on i 0
sleep 0.5
echo ""

# =============================================================================
# SAMPLE PLAYBACK (slots 1-16)
# =============================================================================

echo "--- Sample Slot Tests ---"

# Check if we have an audio file to test with
if [ -f "../tscale/audio.wav" ]; then
    SAMPLE_PATH="$(cd ../tscale && pwd)/audio.wav"
    echo "Test 4: Load and trigger sample from $SAMPLE_PATH"

    osc /sample/1/load s "$SAMPLE_PATH"
    sleep 0.5

    echo "  Setting sample gain to 0.4, channel 4"
    osc /sample/1/gain f 0.4
    osc /sample/1/chan i 3       # channel 4 (0-indexed)

    echo "  Triggering sample playback..."
    osc /sample/1/trig
    sleep 2.0

    echo "  Stopping sample..."
    osc /sample/1/stop
    sleep 0.5
else
    echo "Test 4: SKIPPED (no audio.wav found in ../tscale/)"
fi
echo ""

# =============================================================================
# ADVANCED: Filter sweep
# =============================================================================

echo "--- Filter Sweep Test ---"
echo "Voice with lowpass filter sweep (200Hz -> 2000Hz)"

osc /synth/4/wave i 1          # pulse
osc /synth/4/freq f 110.0      # A2
osc /synth/4/gain f 0.25
osc /synth/4/chan i 2          # channel 3
osc /synth/4/on i 1

# Enable lowpass on channel 3
osc /ch/3/filter i 1 f 200.0 f 2.0  # LP, 200Hz, Q=2.0

echo "  Sweeping filter cutoff..."
for freq in 200 400 600 800 1000 1200 1500 2000; do
    echo "    $freq Hz"
    osc /ch/3/filter i 1 f "$freq" f 2.0
    sleep 0.3
done

osc /synth/4/on i 0
osc /ch/3/filter i 0 f 1000.0 f 0.707  # turn off filter
sleep 0.5
echo ""

# =============================================================================
# CLEANUP
# =============================================================================

echo "--- Cleanup ---"
echo "Resetting all voices and master gain"
for i in {1..8}; do
    osc /synth/$i/on i 0
done
osc /master/gain f 0.8
echo ""

echo "=== Test Complete ==="
echo ""
echo "Quick Reference - Basic OSC Commands:"
echo ""
echo "Master:"
echo "  oscsend localhost 9000 /master/gain f 0.8"
echo ""
echo "Channels (1-4):"
echo "  oscsend localhost 9000 /ch/1/gain f 1.0"
echo "  oscsend localhost 9000 /ch/1/pan f -0.5        # -1=left, +1=right"
echo "  oscsend localhost 9000 /ch/1/filter i 1 f 800.0 f 1.0  # type(1=LP), cutoff, Q"
echo ""
echo "Synth Voices (1-8):"
echo "  oscsend localhost 9000 /synth/1/on i 1         # turn on"
echo "  oscsend localhost 9000 /synth/1/wave i 0       # 0=sine, 1=pulse"
echo "  oscsend localhost 9000 /synth/1/freq f 440.0   # frequency in Hz"
echo "  oscsend localhost 9000 /synth/1/gain f 0.3     # amplitude"
echo "  oscsend localhost 9000 /synth/1/chan i 0       # channel 0-3"
echo "  oscsend localhost 9000 /synth/1/spike          # inject spike (for LIF)"
echo "  oscsend localhost 9000 /synth/1/tau f 0.005 f 0.02  # LIF time constants"
echo ""
echo "Sample Slots (1-16):"
echo "  oscsend localhost 9000 /sample/1/load s \"/path/to/file.wav\""
echo "  oscsend localhost 9000 /sample/1/trig          # trigger playback"
echo "  oscsend localhost 9000 /sample/1/stop          # stop playback"
echo "  oscsend localhost 9000 /sample/1/gain f 0.5"
echo "  oscsend localhost 9000 /sample/1/chan i 0      # assign to channel"
echo ""
