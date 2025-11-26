// tscale.c — Tau-Scale Synaptic Pulse Detector (TS-SPD) using miniaudio
// Build (macOS/Linux):
//   clang -std=c11 -O3 -o tscale tscale.c -lm
//   // macOS 12+: warnings are suppressed in-code; alternatively add -Wno-deprecated-declarations
// Usage:
//   ./tscale -i input.{wav,mp3} [-ta 0.001] [-tr 0.005] [-norm l2|area|none]
//            [-sym] [-mode conv|iir] [-th 3.0] [-ref 0.015] [-o out.txt]
// Output (TSV):
//   t    y    env    evt
//   t=seconds, y=filtered, env=|y| (zero-phase if -sym), evt∈{0,1}
//
// Model:
//   k(t)=exp(−t/τr)−exp(−t/τa), 0<τa<τr.
//   conv: y = x * k (causal); -sym → forward/backward (zero-phase).
//   iir : y = LP(τr) − LP(τa), α=exp(−dt/τ); -sym → forward/backward.
//   Normalization: l2 (unit RMS), area (∑k=1), none.
//   Detector: env > μ + λ·σ with EMA μ,σ and refractory.

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

typedef enum { NORM_L2, NORM_AREA, NORM_NONE } norm_t;
typedef enum { MODE_CONV, MODE_IIR } filt_mode_t;   // renamed from mode_t

typedef struct {
    const char* inpath;
    const char* outpath;
    double tau_a;        // seconds
    double tau_r;        // seconds
    norm_t norm;
    int zero_phase;      // -sym
    filt_mode_t mode;
    double thr_lambda;   // σ units
    double ref_sec;      // refractory seconds
} args_t;

static void die(const char* msg){
    fprintf(stderr, "error: %s\n", msg);
    exit(1);
}

static int parse_norm(const char* s, norm_t* out){
    if (!strcmp(s,"l2"))   { *out=NORM_L2;   return 0; }
    if (!strcmp(s,"area")) { *out=NORM_AREA; return 0; }
    if (!strcmp(s,"none")) { *out=NORM_NONE; return 0; }
    return -1;
}

static int parse_mode(const char* s, filt_mode_t* out){
    if (!strcmp(s,"conv")) { *out=MODE_CONV; return 0; }
    if (!strcmp(s,"iir"))  { *out=MODE_IIR;  return 0; }
    return -1;
}

static void usage_exit(const char* argv0){
    fprintf(stderr,
"Usage: %s -i input.wav|mp3 [options]\n"
"  -o out.txt     Output path (default stdout)\n"
"  -ta s          Attack tau seconds (default 0.001)\n"
"  -tr s          Recovery tau seconds (default 0.005)\n"
"  -norm m        l2|area|none (default l2)\n"
"  -sym           Zero-phase forward/backward (offline)\n"
"  -mode m        conv|iir (default iir)\n"
"  -th x          Threshold in sigma units (default 3.0)\n"
"  -ref s         Refractory window seconds (default 0.015)\n", argv0);
    exit(0);
}

static void parse_args(int argc, char** argv, args_t* a){
    a->inpath=NULL; a->outpath=NULL;
    a->tau_a=1e-3; a->tau_r=5e-3;
    a->norm=NORM_L2; a->zero_phase=0;
    a->mode=MODE_IIR;
    a->thr_lambda=3.0;
    a->ref_sec=0.015;
    for (int i=1;i<argc;i++){
        if (!strcmp(argv[i],"-i") && i+1<argc) a->inpath=argv[++i];
        else if (!strcmp(argv[i],"-o") && i+1<argc) a->outpath=argv[++i];
        else if (!strcmp(argv[i],"-ta") && i+1<argc) a->tau_a=strtod(argv[++i],NULL);
        else if (!strcmp(argv[i],"-tr") && i+1<argc) a->tau_r=strtod(argv[++i],NULL);
        else if (!strcmp(argv[i],"-norm") && i+1<argc){
            if (parse_norm(argv[++i],&a->norm)) die("bad -norm (l2|area|none)");
        } else if (!strcmp(argv[i],"-sym")) a->zero_phase=1;
        else if (!strcmp(argv[i],"-mode") && i+1<argc){
            if (parse_mode(argv[++i],&a->mode)) die("bad -mode (conv|iir)");
        } else if (!strcmp(argv[i],"-th") && i+1<argc) a->thr_lambda=strtod(argv[++i],NULL);
        else if (!strcmp(argv[i],"-ref") && i+1<argc) a->ref_sec=strtod(argv[++i],NULL);
        else if (!strcmp(argv[i],"-h") || !strcmp(argv[i],"--help")) usage_exit(argv[0]);
        else die("unknown argument");
    }
    if (!a->inpath) die("missing -i input");
    if (!(a->tau_a>0 && a->tau_r>0 && a->tau_a<a->tau_r)) die("require 0<tau_a<tau_r");
}

static float* decode_file(const char* path, ma_uint64* frames, ma_uint32* rate){
    ma_decoder_config cfg = ma_decoder_config_init(ma_format_f32, 1, 0); // mono mixdown
    ma_decoder dec;
    if (ma_decoder_init_file(path, &cfg, &dec) != MA_SUCCESS) die("decoder init failed");
    *rate = dec.outputSampleRate;

    const size_t CHUNK = 8192;
    size_t cap = 1<<20; // ~1M frames initial
    float* buf = (float*)malloc(cap*sizeof(float));
    if (!buf){ ma_decoder_uninit(&dec); die("oom"); }
    ma_uint64 total=0;

    for(;;){
        float tmp[CHUNK];
        ma_uint64 got = 0;
        ma_result mr = ma_decoder_read_pcm_frames(&dec, tmp, CHUNK, &got);
        if (mr != MA_SUCCESS && mr != MA_AT_END) { free(buf); ma_decoder_uninit(&dec); die("decode error"); }
        if (got==0) break;
        if (total+got > cap){
            cap = (size_t)((total+got)*1.5 + 65536);
            float* nb = (float*)realloc(buf, cap*sizeof(float));
            if (!nb){ free(buf); ma_decoder_uninit(&dec); die("oom"); }
            buf = nb;
        }
        memcpy(buf+total, tmp, (size_t)got*sizeof(float));
        total += got;
        if (mr == MA_AT_END) break;
    }
    ma_decoder_uninit(&dec);
    *frames = total;
    return buf;
}

static void f32_to_f64(const float* x, int N, double* y){
    for (int i=0;i<N;i++) y[i] = (double)x[i];
}

static void reverse_d(double* a, int n){
    for (int i=0,j=n-1;i<j;i++,j--){ double t=a[i]; a[i]=a[j]; a[j]=t; }
}

/* Kernel generation k[n] for dt=1/fs. Returns length L<=maxL after tail trim. */
static int gen_kernel(double ta, double tr, double fs, double* k, int maxL, norm_t norm){
    const double dt = 1.0/fs;
    const double eps = 1e-3; // ~-60 dB of peak
    int L = maxL;

    double peak=0.0;
    for (int i=0;i<L;i++){
        double t = i*dt;
        k[i] = exp(-t/tr) - exp(-t/ta);
        double a = fabs(k[i]); if (a>peak) peak=a;
    }
    int last = L-1;
    for (int i=L-1;i>=0;i--){ if (fabs(k[i])>=eps*peak){ last=i; break; } }
    L = last+1; if (L<8) L=8; if (L>maxL) L=maxL;

    if (norm==NORM_AREA){
        double s=0.0; for (int i=0;i<L;i++) s+=k[i];
        if (fabs(s)>0){ double c=1.0/s; for (int i=0;i<L;i++) k[i]*=c; }
    } else if (norm==NORM_L2){
        double e2=0.0; for (int i=0;i<L;i++) e2+=k[i]*k[i];
        if (e2>0){ double c=1.0/sqrt(e2); for (int i=0;i<L;i++) k[i]*=c; }
    }
    return L;
}

static void convolve_causal(const double* x, int N, const double* h, int M, double* y){
    for (int n=0;n<N;n++){
        double acc=0.0;
        int jmax = n < (M-1) ? n : (M-1);
        for (int j=0;j<=jmax;j++) acc += x[n-j]*h[j];
        y[n]=acc;
    }
}

/* IIR: y = LP(tr) − LP(ta), α=exp(−dt/τ). */
static void iir_biexp(const double* x, int N, double fs, double ta, double tr, norm_t norm, double* y){
    const double dt = 1.0/fs;
    const double ar = exp(-dt/tr);
    const double aa = exp(-dt/ta);
    double sr=0.0, sa=0.0;

    double gain = 1.0;
    if (norm==NORM_L2){
        double g = hypot(1.0-ar, 1.0-aa); // heuristic RMS for impulse
        if (g>0) gain = 1.0/g;
    } else if (norm==NORM_AREA){
        gain = 1.0;
    }
    for (int n=0;n<N;n++){
        sr = ar*sr + (1.0-ar)*x[n];
        sa = aa*sa + (1.0-aa)*x[n];
        y[n] = (sr - sa)*gain;
    }
}

/* Zero-phase wrappers */
static void zerophase_iir(const double* x, int N, double fs, double ta, double tr, norm_t norm, double* y){
    iir_biexp(x, N, fs, ta, tr, norm, y);
    double* xr = (double*)malloc((size_t)N*sizeof(double));
    double* yb = (double*)malloc((size_t)N*sizeof(double));
    if (!xr || !yb){ free(xr); free(yb); die("oom"); }
    memcpy(xr, x, (size_t)N*sizeof(double));
    reverse_d(xr, N);
    iir_biexp(xr, N, fs, ta, tr, norm, yb);
    reverse_d(yb, N);
    memcpy(y, yb, (size_t)N*sizeof(double));
    free(xr); free(yb);
}

static void zerophase_conv(const double* x, int N, const double* h, int M, double* y){
    convolve_causal(x, N, h, M, y);
    double* yr = (double*)malloc((size_t)N*sizeof(double));
    double* y2 = (double*)malloc((size_t)N*sizeof(double));
    if (!yr || !y2){ free(yr); free(y2); die("oom"); }
    memcpy(yr, y, (size_t)N*sizeof(double));
    reverse_d(yr, N);
    convolve_causal(yr, N, h, M, y2);
    reverse_d(y2, N);
    memcpy(y, y2, (size_t)N*sizeof(double));
    free(yr); free(y2);
}

int main(int argc, char** argv){
    args_t A; parse_args(argc, argv, &A);

    ma_uint64 frames=0; ma_uint32 fs_u=0;
    float* xf32 = decode_file(A.inpath, &frames, &fs_u);
    int N = (int)frames;
    if (N<=0){ free(xf32); die("no samples"); }
    const double fs = (double)fs_u;

    double* x = (double*)malloc((size_t)N*sizeof(double));
    double* y = (double*)malloc((size_t)N*sizeof(double));
    if (!x || !y){ free(xf32); free(x); free(y); die("oom"); }
    for (int i=0;i<N;i++) x[i] = (double)xf32[i];
    free(xf32);

    if (A.mode==MODE_IIR){
        if (A.zero_phase) zerophase_iir(x, N, fs, A.tau_a, A.tau_r, A.norm, y);
        else              iir_biexp   (x, N, fs, A.tau_a, A.tau_r, A.norm, y);
    } else {
        const int KMAX = (int)fmax(8.0, fs * (A.tau_a + A.tau_r) * 10.0 + 1024.0);
        double* h = (double*)malloc((size_t)KMAX*sizeof(double));
        if (!h){ free(x); free(y); die("oom"); }
        int M = gen_kernel(A.tau_a, A.tau_r, fs, h, KMAX, A.norm);
        if (A.zero_phase) zerophase_conv(x, N, h, M, y);
        else              convolve_causal(x, N, h, M, y);
        free(h);
    }

    // Envelope + detector
    const double ema_T = 0.250; // 250 ms
    const double alpha = 1.0 - exp(-1.0/(ema_T*fs));
    double mu=0.0, s2=1e-8;
    const int ref_samp = (int)llround(A.ref_sec * fs);
    int cooldown=0;

    FILE* out = stdout;
    if (A.outpath){ out=fopen(A.outpath,"w"); if(!out){ free(x); free(y); die("cannot open -o"); } }
    fprintf(out, "# fs=%u tau_a=%.6g tau_r=%.6g norm=%d mode=%d sym=%d th=%.3g ref=%.3g\n",
            fs_u, A.tau_a, A.tau_r, (int)A.norm, (int)A.mode, A.zero_phase, A.thr_lambda, A.ref_sec);
    fprintf(out, "t\ty\tenv\tevt\n");

    for (int n=0;n<N;n++){
        const double env = fabs(y[n]);
        mu = (1.0-alpha)*mu + alpha*env;
        const double d = env - mu;
        s2 = (1.0-alpha)*s2 + alpha*(d*d);
        const double sigma = sqrt(fmax(s2, 1e-12));

        int evt = 0;
        if (cooldown>0) cooldown--;
        if (cooldown==0 && env > mu + A.thr_lambda*sigma){
            evt = 1;
            cooldown = ref_samp;
        }
        const double t = (double)n / fs;
        fprintf(out, "%.9f\t%.9f\t%.9f\t%d\n", t, y[n], env, evt);
    }
    if (out!=stdout) fclose(out);

    free(y); free(x);
    return 0;
}
