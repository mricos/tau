// phoneme_analyze.c — Per-phoneme feature extraction for TTS analysis
// Build:
//   clang -std=c11 -O3 -o phoneme_analyze phoneme_analyze.c -lm
// Usage:
//   ./phoneme_analyze -i audio.mp3 [options]
// Options:
//   -o out.json      Output file (default stdout)
//   --tsv            Output TSV time-series instead of JSON
//   --json           Output per-phoneme JSON (default)
//   -win MS          Window size in ms (default 25)
//   -hop MS          Hop size in ms (default 10)
//   -ta SEC          Onset attack tau (default 0.002)
//   -tr SEC          Onset recovery tau (default 0.010)
//   -th SIGMA        Onset threshold (default 2.5)
//
// Output JSON format:
//   {
//     "file": "audio.mp3",
//     "duration_sec": 3.5,
//     "sample_rate": 48000,
//     "phonemes": [
//       {
//         "index": 0,
//         "start_sec": 0.0,
//         "end_sec": 0.15,
//         "duration_ms": 150,
//         "features": {
//           "f0_mean": 220.5,
//           "f0_std": 12.3,
//           "f1_mean": 500.0,
//           "f2_mean": 1800.0,
//           "f3_mean": 2500.0,
//           "energy": 0.0045,
//           "voiced_ratio": 0.85,
//           "spectral_tilt": 2.3
//         }
//       },
//       ...
//     ],
//     "summary": {
//       "f0_mean": 215.0,
//       "phoneme_count": 12,
//       "total_voiced_ratio": 0.72
//     }
//   }

#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdbool.h>

#if defined(__APPLE__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
#endif
#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"
#if defined(__APPLE__)
#pragma clang diagnostic pop
#endif

// ═══════════════════════════════════════════════════════════════════════════════
// CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════════

#define MAX_PHONEMES 1024
#define MAX_FRAMES 100000
#define NUM_FUND_BANDS 4
#define NUM_FORMANT_BANDS 3
#define NUM_BANDS (NUM_FUND_BANDS + NUM_FORMANT_BANDS)

// Filter bank center frequencies
static const double FUND_FREQS[NUM_FUND_BANDS] = {80, 120, 180, 270};
static const double FORMANT_FREQS[NUM_FORMANT_BANDS] = {500, 1500, 2500};
static const double FORMANT_Q[NUM_FORMANT_BANDS] = {3.0, 2.5, 2.0};

// ═══════════════════════════════════════════════════════════════════════════════
// DATA STRUCTURES
// ═══════════════════════════════════════════════════════════════════════════════

typedef struct {
    const char* inpath;
    const char* outpath;
    bool tsv_mode;
    double win_ms;      // Window size in ms
    double hop_ms;      // Hop size in ms
    double tau_a;       // Onset attack tau
    double tau_r;       // Onset recovery tau
    double threshold;   // Onset threshold (sigma)
} Args;

typedef struct {
    double b0, b1, b2;
    double a1, a2;
    double z1, z2;
} Biquad;

typedef struct {
    int index;
    double start_sec;
    double end_sec;
    double duration_ms;
    // Features
    double f0_mean;
    double f0_std;
    double f1_mean;
    double f2_mean;
    double f3_mean;
    double energy;
    double voiced_ratio;
    double spectral_tilt;
} Phoneme;

typedef struct {
    double t;
    double f0;
    double f1, f2, f3;
    double energy;
    double voiced;
    double fund_bands[NUM_FUND_BANDS];
} Frame;

// ═══════════════════════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════════════════════

static void die(const char* msg) {
    fprintf(stderr, "error: %s\n", msg);
    exit(1);
}

static void usage(const char* argv0) {
    fprintf(stderr,
        "Usage: %s -i input.mp3 [options]\n"
        "  -o FILE        Output file (default stdout)\n"
        "  --tsv          Output TSV time-series\n"
        "  --json         Output per-phoneme JSON (default)\n"
        "  -win MS        Window size in ms (default 25)\n"
        "  -hop MS        Hop size in ms (default 10)\n"
        "  -ta SEC        Onset attack tau (default 0.002)\n"
        "  -tr SEC        Onset recovery tau (default 0.010)\n"
        "  -th SIGMA      Onset threshold (default 2.5)\n"
        "\n"
        "Output: Per-phoneme feature extraction with F0, formants, energy\n",
        argv0);
    exit(0);
}

static void parse_args(int argc, char** argv, Args* a) {
    a->inpath = NULL;
    a->outpath = NULL;
    a->tsv_mode = false;
    a->win_ms = 25.0;
    a->hop_ms = 10.0;
    a->tau_a = 0.002;
    a->tau_r = 0.010;
    a->threshold = 2.5;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-i") && i+1 < argc) a->inpath = argv[++i];
        else if (!strcmp(argv[i], "-o") && i+1 < argc) a->outpath = argv[++i];
        else if (!strcmp(argv[i], "--tsv")) a->tsv_mode = true;
        else if (!strcmp(argv[i], "--json")) a->tsv_mode = false;
        else if (!strcmp(argv[i], "-win") && i+1 < argc) a->win_ms = strtod(argv[++i], NULL);
        else if (!strcmp(argv[i], "-hop") && i+1 < argc) a->hop_ms = strtod(argv[++i], NULL);
        else if (!strcmp(argv[i], "-ta") && i+1 < argc) a->tau_a = strtod(argv[++i], NULL);
        else if (!strcmp(argv[i], "-tr") && i+1 < argc) a->tau_r = strtod(argv[++i], NULL);
        else if (!strcmp(argv[i], "-th") && i+1 < argc) a->threshold = strtod(argv[++i], NULL);
        else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) usage(argv[0]);
        else { fprintf(stderr, "Unknown arg: %s\n", argv[i]); usage(argv[0]); }
    }
    if (!a->inpath) die("missing -i input");
}

// ═══════════════════════════════════════════════════════════════════════════════
// AUDIO DECODING
// ═══════════════════════════════════════════════════════════════════════════════

static float* decode_audio(const char* path, ma_uint64* frames, ma_uint32* rate) {
    ma_decoder_config cfg = ma_decoder_config_init(ma_format_f32, 1, 0);
    ma_decoder dec;
    if (ma_decoder_init_file(path, &cfg, &dec) != MA_SUCCESS) die("decoder init failed");
    *rate = dec.outputSampleRate;

    const size_t CHUNK = 8192;
    size_t cap = 1 << 20;
    float* buf = malloc(cap * sizeof(float));
    if (!buf) { ma_decoder_uninit(&dec); die("oom"); }
    ma_uint64 total = 0;

    for (;;) {
        float tmp[CHUNK];
        ma_uint64 got = 0;
        ma_result mr = ma_decoder_read_pcm_frames(&dec, tmp, CHUNK, &got);
        if (mr != MA_SUCCESS && mr != MA_AT_END) { free(buf); ma_decoder_uninit(&dec); die("decode error"); }
        if (got == 0) break;
        if (total + got > cap) {
            cap = (size_t)((total + got) * 1.5 + 65536);
            float* nb = realloc(buf, cap * sizeof(float));
            if (!nb) { free(buf); ma_decoder_uninit(&dec); die("oom"); }
            buf = nb;
        }
        memcpy(buf + total, tmp, got * sizeof(float));
        total += got;
        if (mr == MA_AT_END) break;
    }
    ma_decoder_uninit(&dec);
    *frames = total;
    return buf;
}

// ═══════════════════════════════════════════════════════════════════════════════
// BIQUAD FILTER (RBJ Cookbook bandpass)
// ═══════════════════════════════════════════════════════════════════════════════

static void biquad_bandpass(Biquad* bq, double fs, double fc, double Q) {
    double w0 = 2.0 * M_PI * fc / fs;
    double alpha = sin(w0) / (2.0 * Q);
    double cos_w0 = cos(w0);
    double a0 = 1.0 + alpha;

    bq->b0 = alpha / a0;
    bq->b1 = 0.0;
    bq->b2 = -alpha / a0;
    bq->a1 = -2.0 * cos_w0 / a0;
    bq->a2 = (1.0 - alpha) / a0;
    bq->z1 = 0.0;
    bq->z2 = 0.0;
}

static inline double biquad_process(Biquad* bq, double x) {
    double w = x - bq->a1 * bq->z1 - bq->a2 * bq->z2;
    double y = bq->b0 * w + bq->b1 * bq->z1 + bq->b2 * bq->z2;
    bq->z2 = bq->z1;
    bq->z1 = w;
    return y;
}

static void biquad_reset(Biquad* bq) {
    bq->z1 = 0.0;
    bq->z2 = 0.0;
}

// ═══════════════════════════════════════════════════════════════════════════════
// ONSET DETECTION (from tscale)
// ═══════════════════════════════════════════════════════════════════════════════

static int detect_onsets(const float* audio, int n_samples, double fs,
                         double tau_a, double tau_r, double threshold,
                         double* onsets, int max_onsets) {
    double dt = 1.0 / fs;
    double ar = exp(-dt / tau_r);
    double aa = exp(-dt / tau_a);

    double sr = 0.0, sa = 0.0;
    double* y = malloc(n_samples * sizeof(double));
    if (!y) return 0;

    // IIR bi-exponential filter
    for (int i = 0; i < n_samples; i++) {
        double x = (double)audio[i];
        sr = ar * sr + (1.0 - ar) * x;
        sa = aa * sa + (1.0 - aa) * x;
        y[i] = fabs(sr - sa);
    }

    // Compute envelope statistics
    double sum = 0.0, sum2 = 0.0;
    for (int i = 0; i < n_samples; i++) {
        sum += y[i];
        sum2 += y[i] * y[i];
    }
    double mean = sum / n_samples;
    double var = sum2 / n_samples - mean * mean;
    double std = sqrt(var > 0 ? var : 1e-10);
    double thresh = mean + threshold * std;

    // Detect peaks above threshold with refractory
    int n_onsets = 0;
    int refractory_samples = (int)(0.030 * fs);  // 30ms refractory
    int last_onset = -refractory_samples;

    for (int i = 1; i < n_samples - 1 && n_onsets < max_onsets; i++) {
        if (y[i] > thresh && y[i] > y[i-1] && y[i] >= y[i+1]) {
            if (i - last_onset >= refractory_samples) {
                onsets[n_onsets++] = (double)i / fs;
                last_onset = i;
            }
        }
    }

    free(y);
    return n_onsets;
}

// ═══════════════════════════════════════════════════════════════════════════════
// F0 DETECTION (Autocorrelation method)
// ═══════════════════════════════════════════════════════════════════════════════

static double estimate_f0(const float* window, int win_size, double fs) {
    // F0 range: 50-400 Hz for speech
    int min_lag = (int)(fs / 400.0);
    int max_lag = (int)(fs / 50.0);
    if (max_lag > win_size / 2) max_lag = win_size / 2;

    // Compute autocorrelation
    double r0 = 0.0;
    for (int i = 0; i < win_size; i++) {
        r0 += (double)window[i] * (double)window[i];
    }
    if (r0 < 1e-10) return 0.0;  // Silent

    double best_r = 0.0;
    int best_lag = 0;

    for (int lag = min_lag; lag <= max_lag; lag++) {
        double r = 0.0;
        for (int i = 0; i < win_size - lag; i++) {
            r += (double)window[i] * (double)window[i + lag];
        }
        r /= r0;  // Normalize

        if (r > best_r) {
            best_r = r;
            best_lag = lag;
        }
    }

    // Require reasonable correlation for voiced detection
    if (best_r < 0.3 || best_lag == 0) return 0.0;

    return fs / (double)best_lag;
}

// ═══════════════════════════════════════════════════════════════════════════════
// FRAME ANALYSIS
// ═══════════════════════════════════════════════════════════════════════════════

static void analyze_frames(const float* audio, int n_samples, double fs,
                          double win_ms, double hop_ms,
                          Frame* frames, int* n_frames, int max_frames) {
    int win_samples = (int)(win_ms * fs / 1000.0);
    int hop_samples = (int)(hop_ms * fs / 1000.0);

    // Initialize filter banks
    Biquad fund_filters[NUM_FUND_BANDS];
    Biquad formant_filters[NUM_FORMANT_BANDS];

    for (int b = 0; b < NUM_FUND_BANDS; b++) {
        biquad_bandpass(&fund_filters[b], fs, FUND_FREQS[b], 4.0);
    }
    for (int b = 0; b < NUM_FORMANT_BANDS; b++) {
        biquad_bandpass(&formant_filters[b], fs, FORMANT_FREQS[b], FORMANT_Q[b]);
    }

    *n_frames = 0;
    int pos = 0;

    while (pos + win_samples <= n_samples && *n_frames < max_frames) {
        Frame* f = &frames[*n_frames];
        f->t = (pos + win_samples / 2) / fs;

        // Reset filters for each window (offline mode)
        for (int b = 0; b < NUM_FUND_BANDS; b++) biquad_reset(&fund_filters[b]);
        for (int b = 0; b < NUM_FORMANT_BANDS; b++) biquad_reset(&formant_filters[b]);

        // Process window through filter bank
        double fund_energy[NUM_FUND_BANDS] = {0};
        double formant_energy[NUM_FORMANT_BANDS] = {0};
        double total_energy = 0.0;

        for (int i = 0; i < win_samples; i++) {
            double x = (double)audio[pos + i];
            total_energy += x * x;

            for (int b = 0; b < NUM_FUND_BANDS; b++) {
                double y = biquad_process(&fund_filters[b], x);
                fund_energy[b] += y * y;
            }
            for (int b = 0; b < NUM_FORMANT_BANDS; b++) {
                double y = biquad_process(&formant_filters[b], x);
                formant_energy[b] += y * y;
            }
        }

        // Normalize
        for (int b = 0; b < NUM_FUND_BANDS; b++) {
            f->fund_bands[b] = fund_energy[b] / win_samples;
        }
        f->f1 = formant_energy[0] / win_samples;
        f->f2 = formant_energy[1] / win_samples;
        f->f3 = formant_energy[2] / win_samples;
        f->energy = total_energy / win_samples;

        // F0 estimation
        f->f0 = estimate_f0(&audio[pos], win_samples, fs);
        f->voiced = (f->f0 > 0) ? 1.0 : 0.0;

        (*n_frames)++;
        pos += hop_samples;
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// PHONEME SEGMENTATION
// ═══════════════════════════════════════════════════════════════════════════════

static void segment_phonemes(const Frame* frames, int n_frames,
                            const double* onsets, int n_onsets,
                            double duration,
                            Phoneme* phonemes, int* n_phonemes) {
    *n_phonemes = 0;

    // Add implicit onset at 0 if first onset is late
    double prev_onset = 0.0;
    if (n_onsets > 0 && onsets[0] > 0.05) {
        prev_onset = 0.0;
    } else if (n_onsets > 0) {
        prev_onset = onsets[0];
    }

    for (int i = 0; i <= n_onsets && *n_phonemes < MAX_PHONEMES; i++) {
        double start = prev_onset;
        double end = (i < n_onsets) ? onsets[i] : duration;

        if (i > 0 || (n_onsets > 0 && onsets[0] > 0.05)) {
            // Skip if segment too short
            if (end - start < 0.020) {
                prev_onset = end;
                continue;
            }

            Phoneme* p = &phonemes[*n_phonemes];
            p->index = *n_phonemes;
            p->start_sec = start;
            p->end_sec = end;
            p->duration_ms = (end - start) * 1000.0;

            // Aggregate features from frames in this segment
            double f0_sum = 0.0, f0_sum2 = 0.0;
            double f1_sum = 0.0, f2_sum = 0.0, f3_sum = 0.0;
            double energy_sum = 0.0;
            double voiced_sum = 0.0;
            double low_energy = 0.0, high_energy = 0.0;
            int count = 0;
            int voiced_count = 0;

            for (int f = 0; f < n_frames; f++) {
                if (frames[f].t >= start && frames[f].t < end) {
                    if (frames[f].f0 > 0) {
                        f0_sum += frames[f].f0;
                        f0_sum2 += frames[f].f0 * frames[f].f0;
                        voiced_count++;
                    }
                    f1_sum += frames[f].f1;
                    f2_sum += frames[f].f2;
                    f3_sum += frames[f].f3;
                    energy_sum += frames[f].energy;
                    voiced_sum += frames[f].voiced;

                    low_energy += frames[f].fund_bands[0] + frames[f].fund_bands[1];
                    high_energy += frames[f].fund_bands[2] + frames[f].fund_bands[3];
                    count++;
                }
            }

            if (count > 0) {
                p->f1_mean = f1_sum / count;
                p->f2_mean = f2_sum / count;
                p->f3_mean = f3_sum / count;
                p->energy = energy_sum / count;
                p->voiced_ratio = voiced_sum / count;
                p->spectral_tilt = (low_energy > 1e-10) ? high_energy / low_energy : 0.0;

                if (voiced_count > 0) {
                    p->f0_mean = f0_sum / voiced_count;
                    double var = f0_sum2 / voiced_count - p->f0_mean * p->f0_mean;
                    p->f0_std = sqrt(var > 0 ? var : 0);
                } else {
                    p->f0_mean = 0.0;
                    p->f0_std = 0.0;
                }

                (*n_phonemes)++;
            }
        }
        prev_onset = end;
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// OUTPUT
// ═══════════════════════════════════════════════════════════════════════════════

static void output_tsv(FILE* out, const Frame* frames, int n_frames) {
    fprintf(out, "t\tf0\tf1\tf2\tf3\tenergy\tvoiced\n");
    for (int i = 0; i < n_frames; i++) {
        fprintf(out, "%.6f\t%.2f\t%.9f\t%.9f\t%.9f\t%.9f\t%.0f\n",
                frames[i].t, frames[i].f0,
                frames[i].f1, frames[i].f2, frames[i].f3,
                frames[i].energy, frames[i].voiced);
    }
}

static void output_json(FILE* out, const char* filename, double duration, int sample_rate,
                       const Phoneme* phonemes, int n_phonemes,
                       const Frame* frames, int n_frames) {
    // Compute summary stats
    double f0_sum = 0.0;
    double voiced_sum = 0.0;
    int f0_count = 0;

    for (int i = 0; i < n_phonemes; i++) {
        if (phonemes[i].f0_mean > 0) {
            f0_sum += phonemes[i].f0_mean;
            f0_count++;
        }
        voiced_sum += phonemes[i].voiced_ratio;
    }

    fprintf(out, "{\n");
    fprintf(out, "  \"file\": \"%s\",\n", filename);
    fprintf(out, "  \"duration_sec\": %.6f,\n", duration);
    fprintf(out, "  \"sample_rate\": %d,\n", sample_rate);
    fprintf(out, "  \"phonemes\": [\n");

    for (int i = 0; i < n_phonemes; i++) {
        const Phoneme* p = &phonemes[i];
        fprintf(out, "    {\n");
        fprintf(out, "      \"index\": %d,\n", p->index);
        fprintf(out, "      \"start_sec\": %.6f,\n", p->start_sec);
        fprintf(out, "      \"end_sec\": %.6f,\n", p->end_sec);
        fprintf(out, "      \"duration_ms\": %.2f,\n", p->duration_ms);
        fprintf(out, "      \"features\": {\n");
        fprintf(out, "        \"f0_mean\": %.2f,\n", p->f0_mean);
        fprintf(out, "        \"f0_std\": %.2f,\n", p->f0_std);
        fprintf(out, "        \"f1_mean\": %.9f,\n", p->f1_mean);
        fprintf(out, "        \"f2_mean\": %.9f,\n", p->f2_mean);
        fprintf(out, "        \"f3_mean\": %.9f,\n", p->f3_mean);
        fprintf(out, "        \"energy\": %.9f,\n", p->energy);
        fprintf(out, "        \"voiced_ratio\": %.3f,\n", p->voiced_ratio);
        fprintf(out, "        \"spectral_tilt\": %.4f\n", p->spectral_tilt);
        fprintf(out, "      }\n");
        fprintf(out, "    }%s\n", (i < n_phonemes - 1) ? "," : "");
    }

    fprintf(out, "  ],\n");
    fprintf(out, "  \"summary\": {\n");
    fprintf(out, "    \"f0_mean\": %.2f,\n", (f0_count > 0) ? f0_sum / f0_count : 0.0);
    fprintf(out, "    \"phoneme_count\": %d,\n", n_phonemes);
    fprintf(out, "    \"total_voiced_ratio\": %.3f\n", (n_phonemes > 0) ? voiced_sum / n_phonemes : 0.0);
    fprintf(out, "  }\n");
    fprintf(out, "}\n");
}

// ═══════════════════════════════════════════════════════════════════════════════
// MAIN
// ═══════════════════════════════════════════════════════════════════════════════

int main(int argc, char** argv) {
    Args args;
    parse_args(argc, argv, &args);

    // Decode audio
    ma_uint64 n_frames_audio;
    ma_uint32 sample_rate;
    float* audio = decode_audio(args.inpath, &n_frames_audio, &sample_rate);
    int n_samples = (int)n_frames_audio;
    double duration = (double)n_samples / (double)sample_rate;

    fprintf(stderr, "Loaded: %s (%.2fs, %dHz, %d samples)\n",
            args.inpath, duration, sample_rate, n_samples);

    // Detect onsets
    double* onsets = malloc(MAX_PHONEMES * sizeof(double));
    int n_onsets = detect_onsets(audio, n_samples, (double)sample_rate,
                                  args.tau_a, args.tau_r, args.threshold,
                                  onsets, MAX_PHONEMES);
    fprintf(stderr, "Detected %d onsets\n", n_onsets);

    // Analyze frames
    Frame* frames = malloc(MAX_FRAMES * sizeof(Frame));
    int n_frames = 0;
    analyze_frames(audio, n_samples, (double)sample_rate,
                   args.win_ms, args.hop_ms,
                   frames, &n_frames, MAX_FRAMES);
    fprintf(stderr, "Analyzed %d frames\n", n_frames);

    // Segment into phonemes
    Phoneme* phonemes = malloc(MAX_PHONEMES * sizeof(Phoneme));
    int n_phonemes = 0;
    segment_phonemes(frames, n_frames, onsets, n_onsets, duration,
                     phonemes, &n_phonemes);
    fprintf(stderr, "Segmented %d phonemes\n", n_phonemes);

    // Output
    FILE* out = stdout;
    if (args.outpath) {
        out = fopen(args.outpath, "w");
        if (!out) die("cannot open output file");
    }

    if (args.tsv_mode) {
        output_tsv(out, frames, n_frames);
    } else {
        output_json(out, args.inpath, duration, sample_rate,
                    phonemes, n_phonemes, frames, n_frames);
    }

    if (args.outpath) fclose(out);

    // Cleanup
    free(audio);
    free(onsets);
    free(frames);
    free(phonemes);

    return 0;
}
