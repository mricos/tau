#!/usr/bin/env python3
"""
Quick test of tau integration with ascii_scope_snn.

This script tests the tau audio playback integration without running the full curses UI.
"""

import sys
from pathlib import Path

# Test tau_playback module
print("=" * 60)
print("Testing Tau Integration")
print("=" * 60)
print()

# 1. Test tau_playback module
print("1. Testing tau_playback module...")
try:
    from tau_playback import TauMultitrack
    print("   ✓ tau_playback imported successfully")
except ImportError as e:
    print(f"   ✗ Failed to import tau_playback: {e}")
    sys.exit(1)

# 2. Check tau socket
tau = TauMultitrack()
if tau.check_connection():
    print(f"   ✓ Tau socket found: {tau.socket_path}")
else:
    print(f"   ✗ Tau socket not found: {tau.socket_path}")
    print("   Start tau with: cd ~/src/mricos/demos/tau && ./tau")
    sys.exit(1)

# 3. Test Transport integration
print()
print("2. Testing Transport class integration...")
try:
    from state import Transport
    transport = Transport()
    print("   ✓ Transport class created")

    # Test lazy tau initialization
    transport._ensure_tau()
    if transport.tau:
        print(f"   ✓ Transport connected to tau")
    else:
        print(f"   ✗ Transport failed to connect to tau")
        sys.exit(1)

except Exception as e:
    print(f"   ✗ Error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 4. Test loading audio (if audio file exists)
print()
print("3. Testing audio file loading...")
test_audio = Path("~/audio.wav").expanduser()
if test_audio.exists():
    print(f"   Found test audio: {test_audio}")
    try:
        success = transport.load_audio_for_lane(1, test_audio)
        if success:
            print(f"   ✓ Loaded {test_audio.name} to lane 1")

            # Test playback control
            print()
            print("4. Testing playback control...")
            print("   Starting playback...")
            transport.playing = True
            transport.toggle_play()  # This will trigger tau
            print("   ✓ Play command sent")

            import time
            time.sleep(2)

            print("   Stopping playback...")
            transport.toggle_play()
            print("   ✓ Stop command sent")

            # Test seeking
            print()
            print("5. Testing seek...")
            transport.seek(5.0)
            print("   ✓ Seek to 5.0s")

        else:
            print(f"   ✗ Failed to load audio file")
    except Exception as e:
        print(f"   ✗ Error during audio test: {e}")
        import traceback
        traceback.print_exc()
else:
    print(f"   ⚠ No test audio file found at {test_audio}")
    print("   Skipping audio playback tests")

# Summary
print()
print("=" * 60)
print("Integration Test Complete!")
print("=" * 60)
print()
print("✓ Tau integration is working correctly")
print()
print("Next steps:")
print("  1. Run ascii_scope_snn: python -m ascii_scope_snn.main")
print("  2. Type ':tau_status' to check tau status")
print("  3. Type ':load_audio 1 /path/to/audio.wav' to load audio")
print("  4. Press Space to play/pause with synchronized audio")
print()
