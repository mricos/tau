// filterbank.c — Matched Filter Bank for F0 and Formant Analysis
// Build:
//   clang -std=c11 -O3 -o filterbank filterbank.c -lm
// Usage:
//   ./filterbank -i input.wav|mp3 [-o out.tsv] [-bands N]
// Output (TSV):
//   t  b80  b120  b180  b270  f1  f2  f3  total
//   Time-series of energy in each band
//
// Filter Bank Design:
//   - Fundamental bands: 80, 120, 180, 270 Hz (geometric spacing)
//   - Formant bands: F1 ~500Hz, F2 ~1500Hz, F3 ~2500Hz
//   - Each filter is a 2nd-order IIR bandpass (biquad)
//   - Energy = mean squared output per frame

#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#if defined(__APPLE__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
#endif
#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"
#if defined(__APPLE__)
#pragma clang diagnostic pop
#endif

#define NUM_FUNDAMENTAL_BANDS 4
#define NUM_FORMANT_BANDS 3
#define NUM_BANDS (NUM_FUNDAMENTAL_BANDS + NUM_FORMANT_BANDS)
#define FRAME_SIZE 512  // ~10ms at 48kHz

// Biquad filter state
typedef struct {
    double b0, b1, b2;  // feedforward
    double a1, a2;      // feedback (a0 normalized to 1)
    double z1, z2;      // state
} Biquad;

// Filter bank configuration
typedef struct {
    double center_freq;
    double q;
    Biquad filter;
} Band;

static void die(const char* msg) {
    fprintf(stderr, "error: %s\n", msg);
    exit(1);
}

// Design bandpass biquad filter
// Using RBJ Audio EQ Cookbook formulas
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

// Process one sample through biquad (Direct Form II)
static inline double biquad_process(Biquad* bq, double x) {
    double w = x - bq->a1 * bq->z1 - bq->a2 * bq->z2;
    double y = bq->b0 * w + bq->b1 * bq->z1 + bq->b2 * bq->z2;
    bq->z2 = bq->z1;
    bq->z1 = w;
    return y;
}

// Decode audio file to mono float
static float* decode_file(const char* path, ma_uint64* frames, ma_uint32* rate) {
    ma_decoder_config cfg = ma_decoder_config_init(ma_format_f32, 1, 0);
    ma_decoder dec;
    if (ma_decoder_init_file(path, &cfg, &dec) != MA_SUCCESS) die("decoder init failed");
    *rate = dec.outputSampleRate;

    const size_t CHUNK = 8192;
    size_t cap = 1 << 20;
    float* buf = (float*)malloc(cap * sizeof(float));
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
            float* nb = (float*)realloc(buf, cap * sizeof(float));
            if (!nb) { free(buf); ma_decoder_uninit(&dec); die("oom"); }
            buf = nb;
        }
        memcpy(buf + total, tmp, (size_t)got * sizeof(float));
        total += got;
        if (mr == MA_AT_END) break;
    }
    ma_decoder_uninit(&dec);
    *frames = total;
    return buf;
}

static void usage_exit(const char* argv0) {
    fprintf(stderr,
        "Usage: %s -i input.wav|mp3 [options]\n"
        "  -o out.tsv     Output path (default stdout)\n"
        "  -frame N       Frame size in samples (default 512)\n"
        "  -q Q           Filter Q factor (default 4.0)\n"
        "\n"
        "Output columns:\n"
        "  t      Time (seconds)\n"
        "  b80    Energy in 80Hz band (fundamental)\n"
        "  b120   Energy in 120Hz band\n"
        "  b180   Energy in 180Hz band\n"
        "  b270   Energy in 270Hz band\n"
        "  f1     Energy in F1 band (~500Hz)\n"
        "  f2     Energy in F2 band (~1500Hz)\n"
        "  f3     Energy in F3 band (~2500Hz)\n"
        "  total  Total energy\n", argv0);
    exit(0);
}

int main(int argc, char** argv) {
    const char* inpath = NULL;
    const char* outpath = NULL;
    int frame_size = FRAME_SIZE;
    double Q = 4.0;

    // Parse args
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "-i") && i + 1 < argc) inpath = argv[++i];
        else if (!strcmp(argv[i], "-o") && i + 1 < argc) outpath = argv[++i];
        else if (!strcmp(argv[i], "-frame") && i + 1 < argc) frame_size = atoi(argv[++i]);
        else if (!strcmp(argv[i], "-q") && i + 1 < argc) Q = strtod(argv[++i], NULL);
        else if (!strcmp(argv[i], "-h") || !strcmp(argv[i], "--help")) usage_exit(argv[0]);
        else die("unknown argument");
    }
    if (!inpath) die("missing -i input");

    // Decode audio
    ma_uint64 frames = 0;
    ma_uint32 fs = 0;
    float* audio = decode_file(inpath, &frames, &fs);
    int N = (int)frames;
    if (N <= 0) { free(audio); die("no samples"); }
    double sample_rate = (double)fs;

    // Initialize filter bank
    Band bands[NUM_BANDS];

    // Fundamental detection bands (geometric spacing around speech F0 range)
    double fund_freqs[NUM_FUNDAMENTAL_BANDS] = {80, 120, 180, 270};
    for (int i = 0; i < NUM_FUNDAMENTAL_BANDS; i++) {
        bands[i].center_freq = fund_freqs[i];
        bands[i].q = Q;
        biquad_bandpass(&bands[i].filter, sample_rate, fund_freqs[i], Q);
    }

    // Formant bands
    double formant_freqs[NUM_FORMANT_BANDS] = {500, 1500, 2500};
    double formant_q[NUM_FORMANT_BANDS] = {3.0, 2.5, 2.0};  // Wider Q for formants
    for (int i = 0; i < NUM_FORMANT_BANDS; i++) {
        int idx = NUM_FUNDAMENTAL_BANDS + i;
        bands[idx].center_freq = formant_freqs[i];
        bands[idx].q = formant_q[i];
        biquad_bandpass(&bands[idx].filter, sample_rate, formant_freqs[i], formant_q[i]);
    }

    // Open output
    FILE* out = stdout;
    if (outpath) {
        out = fopen(outpath, "w");
        if (!out) die("cannot open output file");
    }

    // Header
    fprintf(out, "t\tb80\tb120\tb180\tb270\tf1\tf2\tf3\ttotal\n");

    // Process in frames
    int num_frames = N / frame_size;
    for (int f = 0; f < num_frames; f++) {
        double t = (f * frame_size + frame_size / 2) / sample_rate;
        double energies[NUM_BANDS] = {0};
        double total_energy = 0;

        // Process each sample in frame through all filters
        for (int s = 0; s < frame_size; s++) {
            int idx = f * frame_size + s;
            double x = (double)audio[idx];

            for (int b = 0; b < NUM_BANDS; b++) {
                double y = biquad_process(&bands[b].filter, x);
                energies[b] += y * y;  // Accumulate squared output
            }
            total_energy += x * x;
        }

        // Normalize by frame size
        for (int b = 0; b < NUM_BANDS; b++) {
            energies[b] /= frame_size;
        }
        total_energy /= frame_size;

        // Output
        fprintf(out, "%.6f", t);
        for (int b = 0; b < NUM_BANDS; b++) {
            fprintf(out, "\t%.9f", energies[b]);
        }
        fprintf(out, "\t%.9f\n", total_energy);
    }

    if (outpath) fclose(out);
    free(audio);

    return 0;
}
