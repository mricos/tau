#!/usr/bin/env bash
# Build tau audio engine

echo "Building tau..."

clang -std=c11 -O2 tau.c jsmn.c -lpthread \
     -framework AudioToolbox -framework AudioUnit \
     -framework CoreAudio -framework CoreFoundation \
     $(pkg-config --cflags --libs liblo) \
     -o tau

if [ $? -eq 0 ]; then
    echo "✓ tau binary built successfully"
    ls -lh tau
else
    echo "✗ Build failed"
    exit 1
fi
