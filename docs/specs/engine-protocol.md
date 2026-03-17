# tau-engine Protocol Specification

## Overview

tau-engine accepts line-based ASCII commands via Unix socket at `~/tau/runtime/tau.sock`. Each command is a single line terminated by `\n`. Responses are single-line ASCII.

## Transport

- **Socket type**: Unix domain socket (SOCK_STREAM)
- **Default path**: `~/tau/runtime/tau.sock`
- **Encoding**: ASCII, newline-delimited
- **Concurrency**: Single client at a time

## Audio Parameters

- **Sample rate**: 48,000 Hz
- **Buffer size**: 512 frames
- **Format**: Stereo float32
- **Backend**: miniaudio

## Commands

### Master Control

| Command | Description |
|---------|-------------|
| `MASTER <gain>` | Set master volume (0.0-1.0) |
| `STATUS` | Get engine status JSON |
| `QUIT` | Graceful shutdown |

### Channel Control (1-4)

| Command | Description |
|---------|-------------|
| `CH <n> GAIN <value>` | Set channel gain (0.0-1.0) |
| `CH <n> PAN <value>` | Set channel pan (-1.0 to 1.0) |
| `CH <n> FILTER <type> <freq>` | Set channel filter |

### Sample Playback (1-16)

| Command | Description |
|---------|-------------|
| `SAMPLE <n> LOAD <path>` | Load WAV file into slot |
| `SAMPLE <n> TRIG` | Start playback |
| `SAMPLE <n> STOP` | Stop playback |
| `SAMPLE <n> LOOP <0\|1>` | Enable/disable looping |
| `SAMPLE <n> SEEK <position>` | Seek to position (seconds) |

### Synth Voices (1-8)

| Command | Description |
|---------|-------------|
| `VOICE <n> ON` | Enable voice |
| `VOICE <n> OFF` | Disable voice |
| `VOICE <n> FREQ <hz>` | Set frequency |
| `VOICE <n> GAIN <value>` | Set voice gain (0.0-1.0) |

### Recording

| Command | Description |
|---------|-------------|
| `RECORD START` | Begin recording to configured output |
| `RECORD STOP` | Stop recording |
| `RECORD STATUS` | Check recording state |

## Response Format

- **Success**: `OK` or `OK <data>`
- **Error**: `ERR <message>`
- **Status**: JSON object with engine state

## Envelope System (PERC/SUST)

See commit `9127597` for the PERC/SUST envelope system added to the engine.

## Example Session

```
> STATUS
OK {"master":0.8,"channels":4,"samples":16,"voices":8,"recording":false}
> MASTER 0.7
OK
> SAMPLE 1 LOAD /path/to/audio.wav
OK
> SAMPLE 1 TRIG
OK
> SAMPLE 1 STOP
OK
> QUIT
OK
```
