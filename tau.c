// tau.c — Realtime audio engine with Unix datagram socket + OSC control
// Features:
// - 4 mixer channels: gain, pan, per-channel SVF (LP/HP/BP)
// - 16 sample slots (mono one-shots), runtime file load/trigger
// - 8 synth voices: sine or pulse; pulse duty from LIF double-exponential; spike injection
// - Unix datagram socket control (line-based protocol)
// - OSC multicast listener (239.1.1.1:1983) for MIDI-1983 integration
// Build (macOS):
//   clang -std=c11 -O2 tau.c jsmn.c -lpthread \
//     -framework AudioToolbox -framework AudioUnit -framework CoreAudio -framework CoreFoundation \
//     $(pkg-config --cflags --libs liblo) -o tau
// Run:
//   ./tau

#define _DEFAULT_SOURCE
#define _DARWIN_C_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stdatomic.h>
#include <string.h>
#include <strings.h>
#include <math.h>
#include <errno.h>
#include <pthread.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/stat.h>
#include <signal.h>

#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"
#define JSMN_HEADER
#include "jsmn.h"
#include <lo/lo.h>

// ---------- constants ----------
#define ENGINE_SR_DEFAULT   48000u
#define ENGINE_FRAMES_DEF   512u
#define NUM_CHANNELS        4
#define NUM_SLOTS           16
#define NUM_VOICES          8
#define TWO_PI              6.28318530717958647692f
#define MAX_SUBSCRIBERS     32
#define SOCKET_PATH_MAX     108

// ---------- small utils ----------
static inline float clampf(float x, float lo, float hi){ return x<lo?lo:(x>hi?hi:x); }
static inline int   clampi(int v, int lo, int hi){ return v<lo?lo:(v>hi?hi:v); }

// ---------- State Variable Filter (TPT) ----------
typedef enum { F_OFF=0, F_LP=1, F_HP=2, F_BP=3 } FilterType;

typedef struct {
    _Atomic int type;
    _Atomic float cutoff;
    _Atomic float q;
    float ic1eq, ic2eq;
    float g, k;
    float sr;
    float prev_cutoff, prev_q;
} SVF;

static void svf_init(SVF* f, float sr){
    memset(f, 0, sizeof(*f));
    atomic_store(&f->type, F_OFF);
    atomic_store(&f->cutoff, 1000.0f);
    atomic_store(&f->q, 0.7071f);
    f->sr = sr;
    f->prev_cutoff = -1.0f; f->prev_q = -1.0f;
}

static inline void svf_update_coeffs(SVF* f){
    float cutoff = atomic_load(&f->cutoff);
    float q      = clampf(atomic_load(&f->q), 0.1f, 20.0f);
    if (cutoff != f->prev_cutoff || q != f->prev_q){
        float w = (float)M_PI * (cutoff / (f->sr*0.5f));
        f->g = tanf(w);
        f->k = 1.0f / q;
        f->prev_cutoff = cutoff; f->prev_q = q;
    }
}

static inline float svf_process(SVF* f, float x){
    int type = atomic_load(&f->type);
    if (type==F_OFF) return x;
    svf_update_coeffs(f);
    float g=f->g, k=f->k;
    float v0 = x;
    float v1 = (f->ic1eq + g*(v0 - f->ic2eq)) / (1.0f + g*(g + k));
    float v2 = f->ic2eq + g*v1;
    f->ic1eq = 2.0f*v1 - f->ic1eq;
    f->ic2eq = 2.0f*v2 - f->ic2eq;
    switch(type){
        case F_LP: return v2;
        case F_HP: return v0 - k*v1 - v2;
        case F_BP: return v1;
        default:   return v0;
    }
}

// ---------- Mixer Channel ----------
typedef struct {
    _Atomic float gain;
    _Atomic float pan;
    SVF filt;
} Channel;

static void channel_init(Channel* c, float sr){
    atomic_store(&c->gain, 1.0f);
    atomic_store(&c->pan, 0.0f);
    svf_init(&c->filt, sr);
}

static inline void channel_stereo(Channel* c, float mono, float* L, float* R){
    float g = atomic_load(&c->gain);
    float p = clampf(atomic_load(&c->pan), -1.f, 1.f);
    float m = svf_process(&c->filt, mono) * g;
    float lgain = sqrtf(0.5f*(1.f - p));
    float rgain = sqrtf(0.5f*(1.f + p));
    *L += m * lgain;
    *R += m * rgain;
}

// ---------- Sample Slot (one-shot or looping) ----------
typedef struct {
    _Atomic int assignedCh;
    _Atomic int loaded;
    _Atomic int playing;
    _Atomic int loop;           // NEW: Loop playback
    _Atomic float gain;
    float* data;
    uint32_t length;
    _Atomic uint32_t pos;       // Changed to atomic for safe seeking
    ma_decoder decoder;
    _Atomic int haveDecoder;
} SampleSlot;

static void slot_init(SampleSlot* s){
    memset(s, 0, sizeof(*s));
    atomic_store(&s->assignedCh, 0);
    atomic_store(&s->gain, 1.0f);
    atomic_store(&s->loop, 0);
    atomic_store(&s->pos, 0);
}

static void slot_free(SampleSlot* s){
    if (s->data){ free(s->data); s->data=NULL; }
    if (atomic_load(&s->haveDecoder)){ ma_decoder_uninit(&s->decoder); atomic_store(&s->haveDecoder,0); }
    atomic_store(&s->loaded, 0);
    atomic_store(&s->playing, 0);
}

static int slot_load_path(SampleSlot* s, const char* path, uint32_t targetSR){
    slot_free(s);
    ma_decoder_config cfg = ma_decoder_config_init(ma_format_f32, 0, targetSR);
    if (ma_decoder_init_file(path, &cfg, &s->decoder) != MA_SUCCESS) return -1;
    atomic_store(&s->haveDecoder, 1);

    ma_uint64 frames;
    if (ma_decoder_get_length_in_pcm_frames(&s->decoder, &frames) != MA_SUCCESS){ slot_free(s); return -2; }
    ma_uint32 ch = s->decoder.outputChannels;
    float* tmp = (float*)malloc((size_t)frames * ch * sizeof(float));
    if (!tmp){ slot_free(s); return -3; }
    ma_uint64 read = 0;
    ma_decoder_seek_to_pcm_frame(&s->decoder, 0);
    while (read < frames){
        ma_uint64 got = 0;
        ma_decoder_read_pcm_frames(&s->decoder, tmp + (size_t)read*ch, frames - read, &got);
        if (got==0) break;
        read += got;
    }
    s->length = (uint32_t)read;
    s->data = (float*)malloc(s->length * sizeof(float));
    if (!s->data){ free(tmp); slot_free(s); return -4; }
    for (uint32_t i=0;i<s->length;i++){
        double acc=0.0;
        for (uint32_t c=0;c<ch;c++) acc += tmp[(size_t)i*ch + c];
        s->data[i] = (float)(acc / (double)ch);
    }
    free(tmp);
    s->pos = 0;
    atomic_store(&s->loaded, 1);
    return 0;
}

static inline float slot_tick(SampleSlot* s){
    if (!atomic_load(&s->playing) || !atomic_load(&s->loaded) || !s->data) return 0.0f;

    uint32_t pos = atomic_load(&s->pos);

    // Check if reached end
    if (pos >= s->length) {
        if (atomic_load(&s->loop)) {
            // Loop back to start
            pos = 0;
            atomic_store(&s->pos, pos);
        } else {
            // Stop playback
            atomic_store(&s->playing, 0);
            atomic_store(&s->pos, 0);
            return 0.0f;
        }
    }

    float g = atomic_load(&s->gain);
    float v = s->data[pos] * g;
    atomic_store(&s->pos, pos + 1);
    return v;
}

// ---------- Synth Voice ----------
typedef enum { W_SINE=0, W_PULSE=1 } WaveType;

typedef struct {
    _Atomic int on;
    _Atomic int wave;
    _Atomic float freq;
    _Atomic float gain;
    _Atomic int assignedCh;
    _Atomic float tauA;
    _Atomic float tauB;
    _Atomic float dutyBias;
    _Atomic int spikes;
    float phase;
    float sr;
    float Astate, Bstate;
} Voice;

static void voice_init(Voice* v, float sr){
    memset(v, 0, sizeof(*v));
    v->sr = sr;
    atomic_store(&v->on, 0);
    atomic_store(&v->wave, W_SINE);
    atomic_store(&v->freq, 220.0f);
    atomic_store(&v->gain, 0.2f);
    atomic_store(&v->assignedCh, 0);
    atomic_store(&v->tauA, 0.005f);
    atomic_store(&v->tauB, 0.020f);
    atomic_store(&v->dutyBias, 0.5f);
}

static inline float voice_tick(Voice* v){
    if (!atomic_load(&v->on)) return 0.0f;
    int s = atomic_exchange(&v->spikes, 0);
    if (s>0){ v->Astate += (float)s; v->Bstate += (float)s; }

    float f  = fmaxf(1.0f, atomic_load(&v->freq));
    float g  = atomic_load(&v->gain);
    int w    = atomic_load(&v->wave);
    float ta = fmaxf(1e-4f, atomic_load(&v->tauA));
    float tb = fmaxf(1e-4f, atomic_load(&v->tauB));

    float da = expf(-1.0f/(ta*v->sr));
    float db = expf(-1.0f/(tb*v->sr));
    v->Astate *= da;
    v->Bstate *= db;
    float k = v->Astate - v->Bstate;
    float duty = clampf(atomic_load(&v->dutyBias) + 0.25f * k, 0.01f, 0.99f);

    v->phase += f / v->sr;
    if (v->phase >= 1.0f) v->phase -= 1.0f;

    float y = (w==W_SINE) ? sinf(TWO_PI * v->phase) : ((v->phase < duty) ? 1.0f : -1.0f);
    return y * g;
}

// ---------- Engine ----------
typedef struct {
    ma_device device;
    ma_device_config dcfg;
    uint32_t sr;
    uint32_t framesPerBuffer;
    _Atomic float masterGain;

    Channel  ch[NUM_CHANNELS];
    SampleSlot slots[NUM_SLOTS];
    Voice    voices[NUM_VOICES];

    float chMono[NUM_CHANNELS];
} Engine;

static Engine G;

static void data_cb(ma_device* dev, void* pOut, const void* pIn, ma_uint32 nframes){
    (void)dev; (void)pIn;
    float* out = (float*)pOut;
    for (ma_uint32 i=0;i<nframes;i++){
        for (int c=0;c<NUM_CHANNELS;c++) G.chMono[c]=0.0f;

        for (int s=0;s<NUM_SLOTS;s++){
            if (atomic_load(&G.slots[s].playing)){
                int ch = clampi(atomic_load(&G.slots[s].assignedCh), 0, NUM_CHANNELS-1);
                G.chMono[ch] += slot_tick(&G.slots[s]);
            }
        }
        for (int v=0; v<NUM_VOICES; v++){
            if (atomic_load(&G.voices[v].on)){
                int ch = clampi(atomic_load(&G.voices[v].assignedCh), 0, NUM_CHANNELS-1);
                G.chMono[ch] += voice_tick(&G.voices[v]);
            }
        }
        float L=0.f, R=0.f;
        for (int c=0;c<NUM_CHANNELS;c++) channel_stereo(&G.ch[c], G.chMono[c], &L, &R);
        float mg = atomic_load(&G.masterGain);
        out[2*i+0] = L * mg;
        out[2*i+1] = R * mg;
    }
}

// ---------- Datagram Socket Server ----------
typedef struct {
    char path[SOCKET_PATH_MAX];
    int sock;
    pthread_t th;
    volatile int running;

    // Subscriber list
    pthread_mutex_t sub_lock;
    struct sockaddr_un subscribers[MAX_SUBSCRIBERS];
    socklen_t sub_lens[MAX_SUBSCRIBERS];
    int sub_count;
} dgram_srv;

static dgram_srv g_srv;

// ---------- OSC Server ----------
#define OSC_MULTICAST_ADDR "239.1.1.1"
#define OSC_PORT           "1983"

typedef struct {
    lo_server_thread thread;
    volatile int running;
} osc_srv;

static osc_srv g_osc;

// Forward declarations for OSC handlers
static void osc_error(int num, const char *msg, const char *path);
static int osc_handle_mapped(const char *path, const char *types, lo_arg **argv, int argc, lo_message msg, void *user_data);
static int osc_handle_raw_cc(const char *path, const char *types, lo_arg **argv, int argc, lo_message msg, void *user_data);
static int osc_handle_raw_note(const char *path, const char *types, lo_arg **argv, int argc, lo_message msg, void *user_data);

// Add subscriber
static void srv_add_subscriber(const char* path){
    pthread_mutex_lock(&g_srv.sub_lock);

    if (g_srv.sub_count >= MAX_SUBSCRIBERS){
        fprintf(stderr, "Max subscribers reached\n");
        pthread_mutex_unlock(&g_srv.sub_lock);
        return;
    }

    // Check if already subscribed
    for (int i = 0; i < g_srv.sub_count; i++){
        if (strcmp(g_srv.subscribers[i].sun_path, path) == 0){
            pthread_mutex_unlock(&g_srv.sub_lock);
            return; // Already subscribed
        }
    }

    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, path, sizeof(addr.sun_path) - 1);

    g_srv.subscribers[g_srv.sub_count] = addr;
    g_srv.sub_lens[g_srv.sub_count] = sizeof(addr);
    g_srv.sub_count++;

    fprintf(stderr, "Subscriber added: %s (total: %d)\n", path, g_srv.sub_count);
    pthread_mutex_unlock(&g_srv.sub_lock);
}

// Broadcast event to all subscribers
static void srv_broadcast(const char* event){
    pthread_mutex_lock(&g_srv.sub_lock);

    int i = 0;
    while (i < g_srv.sub_count) {
        ssize_t sent = sendto(g_srv.sock, event, strlen(event), MSG_DONTWAIT,
                              (struct sockaddr*)&g_srv.subscribers[i],
                              g_srv.sub_lens[i]);

        if (sent < 0 && (errno == ECONNREFUSED || errno == ENOENT || errno == ENOTCONN)) {
            // Remove dead subscriber
            fprintf(stderr, "Removing dead subscriber: %s\n", g_srv.subscribers[i].sun_path);
            for (int j = i; j < g_srv.sub_count - 1; j++) {
                g_srv.subscribers[j] = g_srv.subscribers[j + 1];
                g_srv.sub_lens[j] = g_srv.sub_lens[j + 1];
            }
            g_srv.sub_count--;
            // Don't increment i - check the same index again
        } else {
            i++;
        }
    }

    pthread_mutex_unlock(&g_srv.sub_lock);
}

// Parse line command and execute
static void process_command(const char* cmd, char* response, size_t resp_size,
                           struct sockaddr_un* client_addr, socklen_t client_len){
    (void)client_addr; (void)client_len;

    char buf[4096];
    strncpy(buf, cmd, sizeof(buf)-1);
    buf[sizeof(buf)-1] = '\0';

    // Tokenize
    char* tokens[32];
    int ntok = 0;
    char* p = strtok(buf, " \t\n");
    while (p && ntok < 32){
        tokens[ntok++] = p;
        p = strtok(NULL, " \t\n");
    }

    if (ntok == 0){
        snprintf(response, resp_size, "ERROR Empty command\n");
        return;
    }

    // INIT
    if (strcmp(tokens[0], "INIT") == 0){
        snprintf(response, resp_size, "OK READY\n");
        return;
    }

    // STATUS
    if (strcmp(tokens[0], "STATUS") == 0){
        snprintf(response, resp_size, "OK STATUS running\n");
        return;
    }

    // SUBSCRIBE <socket_path>
    if (strcmp(tokens[0], "SUBSCRIBE") == 0){
        if (ntok < 2){
            snprintf(response, resp_size, "ERROR Missing socket path\n");
            return;
        }
        srv_add_subscriber(tokens[1]);
        snprintf(response, resp_size, "OK Subscribed\n");
        return;
    }

    // MASTER <gain>
    if (strcmp(tokens[0], "MASTER") == 0){
        if (ntok < 2){
            snprintf(response, resp_size, "ERROR Missing gain value\n");
            return;
        }
        float gain = clampf(atof(tokens[1]), 0.0f, 10.0f);
        atomic_store(&G.masterGain, gain);
        snprintf(response, resp_size, "OK MASTER %.3f\n", gain);

        // Broadcast event
        char event[256];
        snprintf(event, sizeof(event), "EVENT MASTER %.3f\n", gain);
        srv_broadcast(event);
        return;
    }

    // CH <n> <param> <value>
    if (strcmp(tokens[0], "CH") == 0){
        if (ntok < 3){
            snprintf(response, resp_size, "ERROR CH <n> <param> <value>\n");
            return;
        }
        int ch = atoi(tokens[1]);
        if (ch < 1 || ch > NUM_CHANNELS){
            snprintf(response, resp_size, "ERROR Invalid channel %d\n", ch);
            return;
        }
        Channel* C = &G.ch[ch-1];

        if (strcmp(tokens[2], "GAIN") == 0){
            if (ntok < 4){
                snprintf(response, resp_size, "ERROR Missing gain value\n");
                return;
            }
            float gain = clampf(atof(tokens[3]), 0.0f, 10.0f);
            atomic_store(&C->gain, gain);
            snprintf(response, resp_size, "OK CH %d GAIN %.3f\n", ch, gain);

            char event[256];
            snprintf(event, sizeof(event), "EVENT CHANNEL %d GAIN %.3f\n", ch, gain);
            srv_broadcast(event);
            return;
        }

        if (strcmp(tokens[2], "PAN") == 0){
            if (ntok < 4){
                snprintf(response, resp_size, "ERROR Missing pan value\n");
                return;
            }
            float pan = clampf(atof(tokens[3]), -1.0f, 1.0f);
            atomic_store(&C->pan, pan);
            snprintf(response, resp_size, "OK CH %d PAN %.3f\n", ch, pan);

            char event[256];
            snprintf(event, sizeof(event), "EVENT CHANNEL %d PAN %.3f\n", ch, pan);
            srv_broadcast(event);
            return;
        }

        if (strcmp(tokens[2], "FILTER") == 0){
            if (ntok < 6){
                snprintf(response, resp_size, "ERROR FILTER <type> <cutoff> <q>\n");
                return;
            }
            int type = clampi(atoi(tokens[3]), F_OFF, F_BP);
            float cutoff = fmaxf(20.0f, atof(tokens[4]));
            float q = fmaxf(0.1f, atof(tokens[5]));

            atomic_store(&C->filt.type, type);
            atomic_store(&C->filt.cutoff, cutoff);
            atomic_store(&C->filt.q, q);

            snprintf(response, resp_size, "OK CH %d FILTER %d %.1f %.3f\n", ch, type, cutoff, q);
            return;
        }

        snprintf(response, resp_size, "ERROR Unknown CH param: %s\n", tokens[2]);
        return;
    }

    // VOICE <n> <cmd> [args...]
    if (strcmp(tokens[0], "VOICE") == 0){
        if (ntok < 3){
            snprintf(response, resp_size, "ERROR VOICE <n> <cmd>\n");
            return;
        }
        int vi = atoi(tokens[1]);
        if (vi < 1 || vi > NUM_VOICES){
            snprintf(response, resp_size, "ERROR Invalid voice %d\n", vi);
            return;
        }
        Voice* V = &G.voices[vi-1];

        if (strcmp(tokens[2], "ON") == 0){
            atomic_store(&V->on, 1);
            snprintf(response, resp_size, "OK VOICE %d ON\n", vi);

            char event[256];
            snprintf(event, sizeof(event), "EVENT VOICE %d ON\n", vi);
            srv_broadcast(event);
            return;
        }

        if (strcmp(tokens[2], "OFF") == 0){
            atomic_store(&V->on, 0);
            snprintf(response, resp_size, "OK VOICE %d OFF\n", vi);

            char event[256];
            snprintf(event, sizeof(event), "EVENT VOICE %d OFF\n", vi);
            srv_broadcast(event);
            return;
        }

        if (strcmp(tokens[2], "WAVE") == 0){
            if (ntok < 4){
                snprintf(response, resp_size, "ERROR Missing wave value\n");
                return;
            }
            int wave = atoi(tokens[3]) ? W_PULSE : W_SINE;
            atomic_store(&V->wave, wave);
            snprintf(response, resp_size, "OK VOICE %d WAVE %d\n", vi, wave);
            return;
        }

        if (strcmp(tokens[2], "FREQ") == 0){
            if (ntok < 4){
                snprintf(response, resp_size, "ERROR Missing frequency\n");
                return;
            }
            float freq = fmaxf(1.0f, atof(tokens[3]));
            atomic_store(&V->freq, freq);
            snprintf(response, resp_size, "OK VOICE %d FREQ %.2f\n", vi, freq);
            return;
        }

        if (strcmp(tokens[2], "GAIN") == 0){
            if (ntok < 4){
                snprintf(response, resp_size, "ERROR Missing gain\n");
                return;
            }
            float gain = clampf(atof(tokens[3]), 0.0f, 2.0f);
            atomic_store(&V->gain, gain);
            snprintf(response, resp_size, "OK VOICE %d GAIN %.3f\n", vi, gain);
            return;
        }

        if (strcmp(tokens[2], "CHAN") == 0){
            if (ntok < 4){
                snprintf(response, resp_size, "ERROR Missing channel\n");
                return;
            }
            int ch = clampi(atoi(tokens[3]), 0, NUM_CHANNELS-1);
            atomic_store(&V->assignedCh, ch);
            snprintf(response, resp_size, "OK VOICE %d CHAN %d\n", vi, ch);
            return;
        }

        if (strcmp(tokens[2], "SPIKE") == 0){
            atomic_fetch_add(&V->spikes, 1);
            snprintf(response, resp_size, "OK VOICE %d SPIKE\n", vi);
            return;
        }

        if (strcmp(tokens[2], "TAU") == 0){
            if (ntok < 5){
                snprintf(response, resp_size, "ERROR TAU <tau_a> <tau_b>\n");
                return;
            }
            float ta = fmaxf(1e-4f, atof(tokens[3]));
            float tb = fmaxf(1e-4f, atof(tokens[4]));
            atomic_store(&V->tauA, ta);
            atomic_store(&V->tauB, tb);
            snprintf(response, resp_size, "OK VOICE %d TAU %.4f %.4f\n", vi, ta, tb);
            return;
        }

        snprintf(response, resp_size, "ERROR Unknown VOICE cmd: %s\n", tokens[2]);
        return;
    }

    // SAMPLE <n> <cmd> [args...]
    if (strcmp(tokens[0], "SAMPLE") == 0){
        if (ntok < 3){
            snprintf(response, resp_size, "ERROR SAMPLE <n> <cmd>\n");
            return;
        }
        int si = atoi(tokens[1]);
        if (si < 1 || si > NUM_SLOTS){
            snprintf(response, resp_size, "ERROR Invalid sample slot %d\n", si);
            return;
        }
        SampleSlot* S = &G.slots[si-1];

        if (strcmp(tokens[2], "LOAD") == 0){
            if (ntok < 4){
                snprintf(response, resp_size, "ERROR Missing path\n");
                return;
            }
            // Reconstruct path (may have spaces) with bounds checking
            char path[1024] = "";
            size_t path_len = 0;
            for (int i = 3; i < ntok; i++){
                if (i > 3) {
                    size_t space_needed = path_len + 1; // +1 for space
                    if (space_needed >= sizeof(path) - 1) {
                        snprintf(response, resp_size, "ERROR Path too long\n");
                        return;
                    }
                    strcat(path, " ");
                    path_len++;
                }
                size_t token_len = strlen(tokens[i]);
                if (path_len + token_len >= sizeof(path) - 1) {
                    snprintf(response, resp_size, "ERROR Path too long\n");
                    return;
                }
                strcat(path, tokens[i]);
                path_len += token_len;
            }
            int ret = slot_load_path(S, path, G.sr);
            if (ret != 0){
                snprintf(response, resp_size, "ERROR Failed to load: %s (code %d)\n", path, ret);
                return;
            }
            snprintf(response, resp_size, "OK SAMPLE %d LOADED %s\n", si, path);
            return;
        }

        if (strcmp(tokens[2], "TRIG") == 0){
            if (!atomic_load(&S->loaded)){
                snprintf(response, resp_size, "ERROR Sample %d not loaded\n", si);
                return;
            }
            atomic_store(&S->playing, 1);
            S->pos = 0;
            snprintf(response, resp_size, "OK SAMPLE %d TRIG\n", si);

            char event[256];
            snprintf(event, sizeof(event), "EVENT SAMPLE %d PLAYING\n", si);
            srv_broadcast(event);
            return;
        }

        if (strcmp(tokens[2], "STOP") == 0){
            atomic_store(&S->playing, 0);
            S->pos = 0;
            snprintf(response, resp_size, "OK SAMPLE %d STOP\n", si);
            return;
        }

        if (strcmp(tokens[2], "GAIN") == 0){
            if (ntok < 4){
                snprintf(response, resp_size, "ERROR Missing gain\n");
                return;
            }
            float gain = clampf(atof(tokens[3]), 0.0f, 10.0f);
            atomic_store(&S->gain, gain);
            snprintf(response, resp_size, "OK SAMPLE %d GAIN %.3f\n", si, gain);
            return;
        }

        if (strcmp(tokens[2], "CHAN") == 0){
            if (ntok < 4){
                snprintf(response, resp_size, "ERROR Missing channel\n");
                return;
            }
            int ch = clampi(atoi(tokens[3]), 0, NUM_CHANNELS-1);
            atomic_store(&S->assignedCh, ch);
            snprintf(response, resp_size, "OK SAMPLE %d CHAN %d\n", si, ch);
            return;
        }

        if (strcmp(tokens[2], "LOOP") == 0){
            if (ntok < 4){
                snprintf(response, resp_size, "ERROR Missing loop value (0 or 1)\n");
                return;
            }
            int loop = atoi(tokens[3]) ? 1 : 0;
            atomic_store(&S->loop, loop);
            snprintf(response, resp_size, "OK SAMPLE %d LOOP %d\n", si, loop);
            return;
        }

        if (strcmp(tokens[2], "SEEK") == 0){
            if (ntok < 4){
                snprintf(response, resp_size, "ERROR Missing seek time\n");
                return;
            }
            if (!atomic_load(&S->loaded)){
                snprintf(response, resp_size, "ERROR Sample %d not loaded\n", si);
                return;
            }
            float time = fmaxf(0.0f, atof(tokens[3]));
            uint32_t target_pos = (uint32_t)(time * G.sr);
            if (target_pos >= S->length){
                target_pos = S->length > 0 ? S->length - 1 : 0;
            }
            atomic_store(&S->pos, target_pos);
            float actual_time = (float)target_pos / (float)G.sr;
            snprintf(response, resp_size, "OK SAMPLE %d SEEK %.3f\n", si, actual_time);
            return;
        }

        snprintf(response, resp_size, "ERROR Unknown SAMPLE cmd: %s\n", tokens[2]);
        return;
    }

    // QUIT
    if (strcmp(tokens[0], "QUIT") == 0){
        snprintf(response, resp_size, "OK Shutting down\n");
        g_srv.running = 0;
        return;
    }

    snprintf(response, resp_size, "ERROR Unknown command: %s\n", tokens[0]);
}

static void* dgram_thread(void* arg){
    (void)arg;
    char buf[4096];
    char response[4096];
    struct sockaddr_un client_addr;
    socklen_t client_len;

    fprintf(stderr, "Datagram server ready: %s\n", g_srv.path);

    while (g_srv.running){
        client_len = sizeof(client_addr);
        ssize_t n = recvfrom(g_srv.sock, buf, sizeof(buf)-1, 0,
                            (struct sockaddr*)&client_addr, &client_len);

        if (n <= 0){
            if (errno == EINTR) continue;
            usleep(1000);
            continue;
        }

        buf[n] = '\0';

        // Process command
        process_command(buf, response, sizeof(response), &client_addr, client_len);

        // Send response back to client
        if (client_addr.sun_family == AF_UNIX){
            sendto(g_srv.sock, response, strlen(response), 0,
                   (struct sockaddr*)&client_addr, client_len);
        }
    }

    return NULL;
}

static int dgram_start(dgram_srv* s, const char* socket_path){
    memset(s, 0, sizeof(*s));
    strncpy(s->path, socket_path, sizeof(s->path)-1);
    s->running = 1;
    pthread_mutex_init(&s->sub_lock, NULL);

    // Create socket
    s->sock = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (s->sock < 0){
        perror("socket");
        return -1;
    }

    // Check if socket exists and is stale
    struct stat st;
    if (stat(socket_path, &st) == 0) {
        // Socket exists - try to connect to see if it's alive
        int test_sock = socket(AF_UNIX, SOCK_DGRAM, 0);
        if (test_sock >= 0) {
            struct sockaddr_un test_addr;
            memset(&test_addr, 0, sizeof(test_addr));
            test_addr.sun_family = AF_UNIX;
            strncpy(test_addr.sun_path, socket_path, sizeof(test_addr.sun_path)-1);

            // Try to send a test message
            char test_msg[] = "STATUS";
            ssize_t sent = sendto(test_sock, test_msg, sizeof(test_msg), MSG_DONTWAIT,
                                  (struct sockaddr*)&test_addr, sizeof(test_addr));
            close(test_sock);

            if (sent < 0 && (errno == ECONNREFUSED || errno == ENOENT)) {
                // Socket is stale - safe to remove
                fprintf(stderr, "Removing stale socket: %s\n", socket_path);
                unlink(socket_path);
            } else {
                // Socket appears to be in use
                fprintf(stderr, "Error: Socket already in use: %s\n", socket_path);
                close(s->sock);
                return -1;
            }
        }
    }

    // Bind
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, socket_path, sizeof(addr.sun_path)-1);

    if (bind(s->sock, (struct sockaddr*)&addr, sizeof(addr)) < 0){
        perror("bind");
        close(s->sock);
        return -2;
    }

    // Set permissions
    chmod(socket_path, 0666);

    // Start thread
    if (pthread_create(&s->th, NULL, dgram_thread, s) != 0){
        perror("pthread_create");
        close(s->sock);
        unlink(socket_path);
        return -3;
    }

    return 0;
}

static void dgram_stop(dgram_srv* s){
    if (!s->running) return;
    s->running = 0;
    shutdown(s->sock, SHUT_RD);
    pthread_join(s->th, NULL);
    close(s->sock);
    unlink(s->path);
    pthread_mutex_destroy(&s->sub_lock);
}

// ---------- OSC Handlers ----------
static void osc_error(int num, const char *msg, const char *path){
    fprintf(stderr, "OSC Error %d in path %s: %s\n", num, path, msg);
}

// Handle mapped/semantic MIDI values: /midi/mapped/{variant}/{semantic}
static int osc_handle_mapped(const char *path, const char *types, lo_arg **argv,
                              int argc, lo_message msg, void *user_data)
{
    (void)types; (void)argc; (void)msg; (void)user_data;

    // Parse: /midi/mapped/a/FILTER_CUTOFF
    char variant[8], semantic[64];
    if (sscanf(path, "/midi/mapped/%7[^/]/%63s", variant, semantic) != 2){
        return 1;
    }

    float value = argv[0]->f;  // Normalized 0.0-1.0

    // Map semantic names to tau parameters
    // These are examples - customize based on your MIDI map

    if (strcmp(semantic, "VOLUME_1") == 0){
        atomic_store(&G.ch[0].gain, value);
    }
    else if (strcmp(semantic, "VOLUME_2") == 0){
        atomic_store(&G.ch[1].gain, value);
    }
    else if (strcmp(semantic, "VOLUME_3") == 0){
        atomic_store(&G.ch[2].gain, value);
    }
    else if (strcmp(semantic, "VOLUME_4") == 0){
        atomic_store(&G.ch[3].gain, value);
    }
    else if (strcmp(semantic, "PAN_1") == 0){
        atomic_store(&G.ch[0].pan, value * 2.0f - 1.0f);  // 0-1 → -1 to 1
    }
    else if (strcmp(semantic, "PAN_2") == 0){
        atomic_store(&G.ch[1].pan, value * 2.0f - 1.0f);
    }
    else if (strcmp(semantic, "FILTER_CUTOFF") == 0){
        // Scale 0-1 to 100-8000 Hz
        float cutoff = 100.0f + value * 7900.0f;
        atomic_store(&G.ch[0].filt.cutoff, cutoff);
    }
    else if (strcmp(semantic, "MASTER_VOLUME") == 0){
        atomic_store(&G.masterGain, value);
    }

    fprintf(stderr, "[OSC] %s = %.3f\n", semantic, value);
    return 0;
}

// Handle raw MIDI CC: /midi/raw/cc/{channel}/{controller}
static int osc_handle_raw_cc(const char *path, const char *types, lo_arg **argv,
                              int argc, lo_message msg, void *user_data)
{
    (void)types; (void)argc; (void)msg; (void)user_data;

    int channel, controller;
    if (sscanf(path, "/midi/raw/cc/%d/%d", &channel, &controller) != 2){
        return 1;
    }

    int value = argv[0]->i;  // 0-127
    float normalized = (float)value / 127.0f;

    // Example: Map CC7 (volume) on channel 1 to master gain
    if (channel == 1 && controller == 7){
        atomic_store(&G.masterGain, normalized);
        fprintf(stderr, "[OSC] Raw CC %d/%d = %d (master gain)\n", channel, controller, value);
    }

    return 0;
}

// Handle raw MIDI notes: /midi/raw/note/{channel}/{note}
static int osc_handle_raw_note(const char *path, const char *types, lo_arg **argv,
                                int argc, lo_message msg, void *user_data)
{
    (void)types; (void)argc; (void)msg; (void)user_data;

    int channel, note;
    if (sscanf(path, "/midi/raw/note/%d/%d", &channel, &note) != 2){
        return 1;
    }

    int velocity = argv[0]->i;  // 0-127, 0 = note off

    // Example: Trigger samples with notes
    if (velocity > 0){
        // Note 36 (C2) triggers sample 1
        if (note == 36 && G.slots[0].loaded){
            atomic_store(&G.slots[0].playing, 1);
            G.slots[0].pos = 0;
            fprintf(stderr, "[OSC] Note %d ON -> Sample 1 TRIG\n", note);
        }
        // Note 38 (D2) triggers sample 2
        else if (note == 38 && G.slots[1].loaded){
            atomic_store(&G.slots[1].playing, 1);
            G.slots[1].pos = 0;
            fprintf(stderr, "[OSC] Note %d ON -> Sample 2 TRIG\n", note);
        }
    }

    return 0;
}

static int osc_start(osc_srv* o){
    memset(o, 0, sizeof(*o));
    o->running = 1;

    fprintf(stderr, "Starting OSC listener on %s:%s\n", OSC_MULTICAST_ADDR, OSC_PORT);

    // Create multicast OSC server thread
    o->thread = lo_server_thread_new_multicast(OSC_MULTICAST_ADDR, OSC_PORT, osc_error);
    if (!o->thread){
        fprintf(stderr, "Failed to create OSC server\n");
        return -1;
    }

    // Get server and register handlers
    lo_server server = lo_server_thread_get_server(o->thread);

    // Register OSC method handlers
    lo_server_add_method(server, "/midi/mapped/*/*", "f", osc_handle_mapped, NULL);
    lo_server_add_method(server, "/midi/raw/cc/*/*", "i", osc_handle_raw_cc, NULL);
    lo_server_add_method(server, "/midi/raw/note/*/*", "i", osc_handle_raw_note, NULL);

    // Start the server thread
    lo_server_thread_start(o->thread);

    fprintf(stderr, "OSC server ready: listening for MIDI events\n");
    return 0;
}

static void osc_stop(osc_srv* o){
    if (!o->thread) return;

    fprintf(stderr, "Stopping OSC server...\n");
    o->running = 0;
    lo_server_thread_stop(o->thread);
    lo_server_thread_free(o->thread);
    o->thread = NULL;
}

// ---------- Engine init/run ----------
static int engine_init(Engine* E, uint32_t sr, uint32_t frames){
    memset(E,0,sizeof(*E));
    E->sr = sr;
    E->framesPerBuffer = frames;
    atomic_store(&E->masterGain, 0.8f);

    for (int c=0;c<NUM_CHANNELS;c++) channel_init(&E->ch[c], (float)sr);
    for (int s=0;s<NUM_SLOTS;s++)    slot_init(&E->slots[s]);
    for (int v=0;v<NUM_VOICES;v++)   voice_init(&E->voices[v], (float)sr);

    E->dcfg = ma_device_config_init(ma_device_type_playback);
    E->dcfg.sampleRate = sr;
    E->dcfg.playback.format   = ma_format_f32;
    E->dcfg.playback.channels = 2;
    E->dcfg.dataCallback = data_cb;
    E->dcfg.performanceProfile = ma_performance_profile_low_latency;
    E->dcfg.periodSizeInFrames = frames;
    if (ma_device_init(NULL, &E->dcfg, &E->device) != MA_SUCCESS) return -1;
    return 0;
}

static void engine_uninit(Engine* E){
    for (int s=0;s<NUM_SLOTS;s++) slot_free(&E->slots[s]);
    ma_device_uninit(&E->device);
}

// ---------- main ----------
int main(int argc, char** argv){
    // Ignore SIGPIPE to prevent crashes when writing to dead sockets
    signal(SIGPIPE, SIG_IGN);

    uint32_t sr = ENGINE_SR_DEFAULT;
    uint32_t frames = ENGINE_FRAMES_DEF;

    // Get socket path from env or use default
    const char* socket_path = getenv("TAU_SOCKET");
    if (!socket_path){
        // Default: ~/tau/runtime/tau.sock
        const char* home = getenv("HOME");
        if (!home) home = "/tmp";
        static char default_path[512];
        snprintf(default_path, sizeof(default_path), "%s/tau/runtime/tau.sock", home);
        socket_path = default_path;

        // Ensure directories exist (create parent first)
        char tau_dir[512];
        snprintf(tau_dir, sizeof(tau_dir), "%s/tau", home);
        mkdir(tau_dir, 0755);

        char runtime_dir[512];
        snprintf(runtime_dir, sizeof(runtime_dir), "%s/tau/runtime", home);
        mkdir(runtime_dir, 0755);
    }

    // Parse args
    for (int i=1; i<argc; i++){
        if (!strcmp(argv[i], "--sr") && i+1<argc){
            sr = (uint32_t)atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--frames") && i+1<argc){
            frames = (uint32_t)atoi(argv[++i]);
        } else if (!strcmp(argv[i], "--socket") && i+1<argc){
            socket_path = argv[++i];
        }
    }

    // Init engine
    if (engine_init(&G, sr, frames) != 0){
        fprintf(stderr, "Engine init failed\n");
        return 1;
    }

    // Start datagram server
    if (dgram_start(&g_srv, socket_path) != 0){
        fprintf(stderr, "Datagram server start failed: %s\n", socket_path);
        engine_uninit(&G);
        return 2;
    }

    // Start OSC server
    if (osc_start(&g_osc) != 0){
        fprintf(stderr, "OSC server start failed\n");
        dgram_stop(&g_srv);
        engine_uninit(&G);
        return 3;
    }

    // Start audio
    if (ma_device_start(&G.device) != MA_SUCCESS){
        fprintf(stderr, "Audio start failed\n");
        osc_stop(&g_osc);
        dgram_stop(&g_srv);
        engine_uninit(&G);
        return 4;
    }

    fprintf(stderr, "tau running: sr=%u frames=%u socket=%s\n",
            G.sr, G.framesPerBuffer, socket_path);
    fprintf(stderr, "Send 'QUIT' command to stop\n");

    // Main loop
    while (g_srv.running){
        sleep(1);
    }

    // Cleanup
    ma_device_stop(&G.device);
    osc_stop(&g_osc);
    dgram_stop(&g_srv);
    engine_uninit(&G);

    fprintf(stderr, "tau stopped\n");
    return 0;
}
