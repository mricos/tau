#!/usr/bin/env bash
# Quick tau test

echo "=== TAU Quick Test ==="

./tau-send "MASTER 0.7" && echo ""
./tau-send "VOICE 1 WAVE 0" && echo ""
./tau-send "VOICE 1 FREQ 440" && echo ""
./tau-send "VOICE 1 GAIN 0.3" && echo ""
./tau-send "VOICE 1 ON" && echo ""

echo "Playing 440Hz for 2 seconds..."
sleep 2

./tau-send "VOICE 1 OFF" && echo ""

echo "✓ Test complete!"
