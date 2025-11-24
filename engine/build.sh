#!/usr/bin/env bash
# Build tau-engine audio engine

echo "Building tau-engine..."

clang -std=c11 -O2 tau-engine.c jsmn.c -lpthread \
     -framework AudioToolbox -framework AudioUnit \
     -framework CoreAudio -framework CoreFoundation \
     $(pkg-config --cflags --libs liblo) \
     -o tau-engine

if [ $? -eq 0 ]; then
    echo "✓ tau-engine binary built successfully"
    ls -lh tau-engine
else
    echo "✗ Build failed"
    exit 1
fi
