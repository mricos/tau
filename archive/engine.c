// engine.c — macOS realtime engine with OSC control, JSON config via jsmn
// Features:
// - 4 mixer channels: gain, pan, per-channel SVF (LP/HP/BP).
// - 16 sample slots (mono one-shots), runtime file load/trigger.
// - 8 synth voices: sine or pulse; pulse duty from LIF double-exponential (tau_a, tau_b); spike injection.
// - OSC UDP control (messages i/f/s). OSC port is read from JSON config only.
// Build (macOS):
//   clang -std=c11 -O2 engine.c jsmn.c -lpthread \
//     -framework AudioToolbox -framework AudioUnit -framework CoreAudio -framework CoreFoundation \
//     -o engine
// Run:
//   ./engine --config engine.json

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
#include <netinet/in.h>
#include <arpa/inet.h>

#define MINIAUDIO_IMPLEMENTATION
#include "miniaudio.h"   // place miniaudio.h next to this file
#define JSMN_HEADER
#include "jsmn.h"        // https://github.com/zserge/jsmn (compile with jsmn.c)

// ---------- constants ----------
#define ENGINE_SR_DEFAULT   48000u
#define ENGINE_FRAMES_DEF   512u
#define NUM_CHANNELS        4
#define NUM_SLOTS           16
#define NUM_VOICES          8
#define TWO_PI              6.28318530717958647692f

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
    _Atomic float gain;   // linear
    _Atomic float pan;    // -1..+1
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

// ---------- Sample Slot (one-shot) ----------
typedef struct {
    _Atomic int assignedCh;     // 0..3
    _Atomic int loaded;         // bool
    _Atomic int playing;        // bool
    _Atomic float gain;         // linear
    float* data;                // mono, f32
    uint32_t length;            // samples
    uint32_t pos;               // cursor
    ma_decoder decoder;
    _Atomic int haveDecoder;
} SampleSlot;

static void slot_init(SampleSlot* s){
    memset(s, 0, sizeof(*s));
    atomic_store(&s->assignedCh, 0);
    atomic_store(&s->gain, 1.0f);
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
    if (s->pos >= s->length){ atomic_store(&s->playing, 0); s->pos = 0; return 0.0f; }
    float g = atomic_load(&s->gain);
    float v = s->data[s->pos++] * g;
    return v;
}

// ---------- Synth Voice ----------
typedef enum { W_SINE=0, W_PULSE=1 } WaveType;

typedef struct {
    _Atomic int on;            // 0/1
    _Atomic int wave;          // W_SINE/W_PULSE
    _Atomic float freq;        // Hz
    _Atomic float gain;        // linear
    _Atomic int assignedCh;    // 0..3
    _Atomic float tauA;        // s
    _Atomic float tauB;        // s
    _Atomic float dutyBias;    // [0,1]
    _Atomic int spikes;        // queued spikes
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

    float chMono[NUM_CHANNELS];   // scratch
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

// ---------- OSC (minimal) ----------
typedef union { int32_t i; float f; const char* s; } osc_arg;

typedef struct {
    char addr[256];
    char types[128];
    osc_arg argv[16];
    int argc;
} osc_msg;

static inline int osc_aligned(int x){ return (x + 3) & ~3; }
static inline uint32_t be32(const unsigned char* p){ return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|((uint32_t)p[3]); }
static int osc_parse(const unsigned char* buf, int len, osc_msg* m){
    memset(m,0,sizeof(*m));
    int a_len = strnlen((const char*)buf, len);
    if (a_len<=0 || a_len>= (int)sizeof(m->addr)) return -1;
    memcpy(m->addr, buf, a_len+1);
    int off = osc_aligned(a_len+1);
    if (off >= len) return -2;
    if (buf[off] != ',') return -3;
    int t_len = strnlen((const char*)buf+off, len-off);
    if (t_len<=0 || t_len >= (int)sizeof(m->types)) return -4;
    memcpy(m->types, buf+off, t_len+1);
    off += osc_aligned(t_len+1);
    m->argc = (int)strlen(m->types)-1;
    if (m->argc > 16) m->argc = 16;
    for (int i=0;i<m->argc;i++){
        char t = m->types[1+i];
        if (off+4 > len) return -5;
        if (t=='i'){
            m->argv[i].i = (int32_t)be32(buf+off); off += 4;
        } else if (t=='f'){
            uint32_t u = be32(buf+off); float f; memcpy(&f, &u, 4); m->argv[i].f = f; off += 4;
        } else if (t=='s'){
            int sl = strnlen((const char*)buf+off, len-off); if (sl<=0) return -6;
            m->argv[i].s = (const char*)buf+off; off += osc_aligned(sl+1);
        } else return -7;
    }
    return 0;
}

typedef struct { int sock; pthread_t th; int port; volatile int running; } osc_srv;

static void* osc_thread(void* arg){
    osc_srv* s = (osc_srv*)arg;
    struct sockaddr_in cli; socklen_t clen = sizeof(cli);
    unsigned char buf[2048];
    while (s->running){
        ssize_t n = recvfrom(s->sock, buf, sizeof(buf), 0, (struct sockaddr*)&cli, &clen);
        if (n<=0) { if (errno==EINTR) continue; usleep(1000); continue; }
        osc_msg msg; if (osc_parse(buf,(int)n,&msg)!=0) continue;

        // Master
        if (strcmp(msg.addr,"/master/gain")==0 && msg.argc>=1 && msg.types[1]=='f'){ atomic_store(&G.masterGain, clampf(msg.argv[0].f, 0.f, 10.f)); continue; }

        // Channel: /ch/{1..4}/(gain|pan|filter)
        int chn=0;
        if (sscanf(msg.addr,"/ch/%d/%*s",&chn)==1 && chn>=1 && chn<=NUM_CHANNELS){
            char what[64]={0}; const char* slash = strrchr(msg.addr,'/'); if (slash) strncpy(what, slash+1, sizeof(what)-1);
            Channel* C = &G.ch[chn-1];
            if (strcmp(what,"gain")==0 && msg.argc>=1 && msg.types[1]=='f'){ atomic_store(&C->gain, clampf(msg.argv[0].f, 0.f, 10.f)); continue; }
            if (strcmp(what,"pan")==0  && msg.argc>=1 && msg.types[1]=='f'){ atomic_store(&C->pan,  clampf(msg.argv[0].f,-1.f,+1.f)); continue; }
            if (strcmp(what,"filter")==0 && msg.argc>=3 && msg.types[1]=='i' && msg.types[2]=='f' && msg.types[3]=='f'){
                atomic_store(&C->filt.type, msg.argv[0].i);
                atomic_store(&C->filt.cutoff, fmaxf(20.f, msg.argv[1].f));
                atomic_store(&C->filt.q, fmaxf(0.1f, msg.argv[2].f));
                continue;
            }
        }

        // Sample slots: /sample/{1..16}/(load|trig|gain|chan|stop)
        int idx=0;
        if (sscanf(msg.addr,"/sample/%d/%*s",&idx)==1 && idx>=1 && idx<=NUM_SLOTS){
            SampleSlot* S = &G.slots[idx-1];
            const char* tail = strrchr(msg.addr,'/'); if (!tail) continue;
            if (strcmp(tail+1,"load")==0 && msg.argc>=1 && msg.types[1]=='s'){ const char* path = msg.argv[0].s; (void)slot_load_path(S, path, G.sr); continue; }
            if (strcmp(tail+1,"trig")==0){ atomic_store(&S->playing, 1); S->pos=0; continue; }
            if (strcmp(tail+1,"gain")==0 && msg.argc>=1 && msg.types[1]=='f'){ atomic_store(&S->gain, clampf(msg.argv[0].f,0.f,10.f)); continue; }
            if (strcmp(tail+1,"chan")==0 && msg.argc>=1 && msg.types[1]=='i'){ atomic_store(&S->assignedCh, clampi(msg.argv[0].i,0,NUM_CHANNELS-1)); continue; }
            if (strcmp(tail+1,"stop")==0){ atomic_store(&S->playing, 0); S->pos=0; continue; }
        }

        // Synth voices: /synth/{1..8}/(on|wave|freq|gain|chan|tau|duty|spike)
        int vi=0;
        if (sscanf(msg.addr,"/synth/%d/%*s",&vi)==1 && vi>=1 && vi<=NUM_VOICES){
            Voice* V = &G.voices[vi-1];
            const char* tail = strrchr(msg.addr,'/'); if (!tail) continue;
            if (strcmp(tail+1,"on")==0   && msg.argc>=1 && msg.types[1]=='i'){ atomic_store(&V->on,   msg.argv[0].i?1:0); continue; }
            if (strcmp(tail+1,"wave")==0 && msg.argc>=1 && msg.types[1]=='i'){ atomic_store(&V->wave, (msg.argv[0].i?W_PULSE:W_SINE)); continue; }
            if (strcmp(tail+1,"freq")==0 && msg.argc>=1 && msg.types[1]=='f'){ atomic_store(&V->freq, fmaxf(1.f,msg.argv[0].f)); continue; }
            if (strcmp(tail+1,"gain")==0 && msg.argc>=1 && msg.types[1]=='f'){ atomic_store(&V->gain, clampf(msg.argv[0].f,0.f,2.f)); continue; }
            if (strcmp(tail+1,"chan")==0 && msg.argc>=1 && msg.types[1]=='i'){ atomic_store(&V->assignedCh, clampi(msg.argv[0].i,0,NUM_CHANNELS-1)); continue; }
            if (strcmp(tail+1,"tau")==0  && msg.argc>=2 && msg.types[1]=='f' && msg.types[2]=='f'){ atomic_store(&V->tauA, fmaxf(1e-4f,msg.argv[0].f)); atomic_store(&V->tauB, fmaxf(1e-4f,msg.argv[1].f)); continue; }
            if (strcmp(tail+1,"duty")==0 && msg.argc>=1 && msg.types[1]=='f'){ atomic_store(&V->dutyBias, clampf(msg.argv[0].f,0.01f,0.99f)); continue; }
            if (strcmp(tail+1,"spike")==0){ atomic_fetch_add(&V->spikes, 1); continue; }
        }
    }
    return NULL;
}
static int osc_start(osc_srv* s, int port){
    memset(s,0,sizeof(*s));
    s->port = port; s->running = 1;
    s->sock = socket(AF_INET, SOCK_DGRAM, 0);
    if (s->sock<0) return -1;
    int yes=1; setsockopt(s->sock,SOL_SOCKET,SO_REUSEADDR,&yes,sizeof(yes));
    struct sockaddr_in sa; memset(&sa,0,sizeof(sa));
    sa.sin_family = AF_INET; sa.sin_port = htons((uint16_t)port); sa.sin_addr.s_addr = htonl(INADDR_ANY);
    if (bind(s->sock,(struct sockaddr*)&sa,sizeof(sa))<0) { close(s->sock); return -2; }
    if (pthread_create(&s->th,NULL,osc_thread,s)!=0){ close(s->sock); return -3; }
    return 0;
}
static void osc_stop(osc_srv* s){
    if (!s->running) return;
    s->running=0; shutdown(s->sock,SHUT_RD);
    pthread_join(s->th,NULL);
    close(s->sock);
}

// ---------- JSON via jsmn ----------
static char* read_file(const char* path, long* out_n){
    FILE* f = fopen(path,"rb"); if (!f) return NULL;
    fseek(f,0,SEEK_END); long n = ftell(f); fseek(f,0,SEEK_SET);
    if (n <= 0 || n > (32L<<20)){ fclose(f); return NULL; }
    char* buf = (char*)malloc((size_t)n+1); if (!buf){ fclose(f); return NULL; }
    if ((long)fread(buf,1,(size_t)n,f) != n){ free(buf); fclose(f); return NULL; }
    fclose(f); buf[n]='\0'; if (out_n) *out_n=n; return buf;
}

static int tok_streq(const char* js, const jsmntok_t* t, const char* s){
    int len = t->end - t->start; return (t->type==JSMN_STRING) && ((int)strlen(s)==len) && (strncmp(js+t->start,s,(size_t)len)==0);
}
static int tok_to_double(const char* js, const jsmntok_t* t, double* out){
    if (t->type!=JSMN_PRIMITIVE && t->type!=JSMN_STRING) return 0;
    char tmp[128]; int len = t->end - t->start; if (len<=0 || len >= (int)sizeof(tmp)) return 0;
    memcpy(tmp, js+t->start, (size_t)len); tmp[len]='\0';
    char* e=NULL; double v = strtod(tmp,&e); if (!e || *e!='\0') return 0; *out=v; return 1;
}
static int tok_to_int(const char* js, const jsmntok_t* t, int* out){
    double d; if (!tok_to_double(js,t,&d)) return 0; *out = (int)llround(d); return 1;
}
static int tok_to_bool(const char* js, const jsmntok_t* t, int* out){
    if (t->type!=JSMN_PRIMITIVE) return 0;
    int len=t->end-t->start;
    if (len==4 && strncmp(js+t->start,"true",4)==0){ *out=1; return 1; }
    if (len==5 && strncmp(js+t->start,"false",5)==0){ *out=0; return 1; }
    return 0;
}
static int tok_is_null(const char* js, const jsmntok_t* t){
    return t->type==JSMN_PRIMITIVE && (t->end-t->start)==4 && strncmp(js+t->start,"null",4)==0;
}
static int tok_next(const jsmntok_t* tok, int i){ // skip subtree; return next index
    int j=i+1, n=1;
    if (tok[i].type==JSMN_PRIMITIVE || tok[i].type==JSMN_STRING) return j;
    while (n>0){ j++; if (tok[j-1].type==JSMN_ARRAY || tok[j-1].type==JSMN_OBJECT) n += tok[j-1].size; n--; }
    return j;
}
static int obj_get(const char* js, const jsmntok_t* tok, int obj_idx, const char* key){
    if (tok[obj_idx].type!=JSMN_OBJECT) return -1;
    int n = tok[obj_idx].size;
    int i = obj_idx+1;
    for (int k=0;k<n;k++){
        if (tok[i].type!=JSMN_STRING) return -1;
        int val = i+1;
        if (tok_streq(js,&tok[i],key)) return val;
        i = tok_next(tok, val);
    }
    return -1;
}
static int array_foreach(const jsmntok_t* tok, int arr_idx, int* it){
    if (tok[arr_idx].type!=JSMN_ARRAY) return 0;
    if (*it==0) *it = arr_idx+1;
    else *it = tok_next(tok, *it);
    int end = tok_next(tok, arr_idx);
    return (*it < end);
}
static int filter_from_string(const char* s){
    if (!s) return F_OFF;
    if (!strcasecmp(s,"lp") || !strcasecmp(s,"lowpass")) return F_LP;
    if (!strcasecmp(s,"hp") || !strcasecmp(s,"highpass")) return F_HP;
    if (!strcasecmp(s,"bp") || !strcasecmp(s,"bandpass")) return F_BP;
    if (!strcasecmp(s,"off")|| !strcasecmp(s,"bypass"))   return F_OFF;
    return F_OFF;
}
static int wave_from_string(const char* s){
    if (!s) return W_SINE;
    if (!strcasecmp(s,"sine"))  return W_SINE;
    if (!strcasecmp(s,"pulse")) return W_PULSE;
    return W_SINE;
}

// Pass 1: read engine.sample_rate, frames_per_buffer, osc_port, master_gain
static int load_config_json_engine(const char* path, uint32_t* sr, uint32_t* frames, int* osc_port, float* master_gain){
    long n=0; char* buf = read_file(path,&n); if (!buf){ fprintf(stderr,"config open failed: %s\n", path); return -1; }
    jsmn_parser p; jsmn_init(&p);
    int tokcap = 1024;
    jsmntok_t* tok = (jsmntok_t*)malloc(sizeof(jsmntok_t)*tokcap);
    int r = jsmn_parse(&p, buf, n, tok, tokcap);
    if (r==JSMN_ERROR_NOMEM){
        free(tok); tokcap = 4096; tok = (jsmntok_t*)malloc(sizeof(jsmntok_t)*tokcap);
        jsmn_init(&p); r = jsmn_parse(&p, buf, n, tok, tokcap);
    }
    if (r<0){ fprintf(stderr,"JSON parse error\n"); free(tok); free(buf); return -2; }

    if (tok[0].type!=JSMN_OBJECT){ free(tok); free(buf); return -3; }
    int eng = obj_get(buf, tok, 0, "engine");
    if (eng>=0){
        int t;
        t = obj_get(buf,tok,eng,"sample_rate");       if (t>=0){ int iv; if (tok_to_int(buf,&tok[t],&iv)) *sr       = (uint32_t)clampi(iv,8000,192000); }
        t = obj_get(buf,tok,eng,"frames_per_buffer"); if (t>=0){ int iv; if (tok_to_int(buf,&tok[t],&iv)) *frames   = (uint32_t)clampi(iv,32,4096); }
        t = obj_get(buf,tok,eng,"osc_port");          if (t>=0){ int iv; if (tok_to_int(buf,&tok[t],&iv)) *osc_port = clampi(iv,1,65535); }
        t = obj_get(buf,tok,eng,"master_gain");       if (t>=0){ double dv; if (tok_to_double(buf,&tok[t],&dv)) *master_gain = clampf((float)dv,0.f,10.f); }
    }

    free(tok); free(buf); return 0;
}

// Pass 2: apply channels/slots/voices after engine_init()
static int load_config_json_apply(const char* path, uint32_t targetSR){
    long n=0; char* buf = read_file(path,&n); if (!buf){ fprintf(stderr,"config open failed: %s\n", path); return -1; }
    jsmn_parser p; jsmn_init(&p);
    int tokcap = 4096;
    jsmntok_t* tok = (jsmntok_t*)malloc(sizeof(jsmntok_t)*tokcap);
    int r = jsmn_parse(&p, buf, n, tok, tokcap);
    if (r<0){ fprintf(stderr,"JSON parse error\n"); free(tok); free(buf); return -2; }

    if (tok[0].type!=JSMN_OBJECT){ free(tok); free(buf); return -3; }

    // engine.master_gain reapply if present
    int eng = obj_get(buf,tok,0,"engine");
    if (eng>=0){
        int t = obj_get(buf,tok,eng,"master_gain"); if (t>=0){ double dv; if (tok_to_double(buf,&tok[t],&dv)) atomic_store(&G.masterGain, clampf((float)dv,0.f,10.f)); }
    }

    // channels[]
    int carr = obj_get(buf,tok,0,"channels");
    if (carr>=0 && tok[carr].type==JSMN_ARRAY){
        int it=0, idx=0;
        while (array_foreach(tok, carr, &it) && idx<NUM_CHANNELS){
            if (tok[it].type!=JSMN_OBJECT){ it = tok_next(tok,it); continue; }
            Channel* C = &G.ch[idx++];
            int t; double d; int iv;
            t = obj_get(buf,tok,it,"gain");   if (t>=0 && tok_to_double(buf,&tok[t],&d)) atomic_store(&C->gain,(float)clampf((float)d,0.f,10.f));
            t = obj_get(buf,tok,it,"pan");    if (t>=0 && tok_to_double(buf,&tok[t],&d)) atomic_store(&C->pan,(float)clampf((float)d,-1.f,+1.f));
            t = obj_get(buf,tok,it,"filter");
            if (t>=0){
                if (tok[t].type==JSMN_STRING){
                    int len = tok[t].end - tok[t].start; char tmp[32]; if (len>(int)sizeof(tmp)-1) len=sizeof(tmp)-1;
                    memcpy(tmp, buf+tok[t].start, (size_t)len); tmp[len]='\0';
                    atomic_store(&C->filt.type, filter_from_string(tmp));
                } else if (tok_to_int(buf,&tok[t],&iv)) {
                    atomic_store(&C->filt.type, clampi(iv,F_OFF,F_BP));
                }
            }
            t = obj_get(buf,tok,it,"cutoff"); if (t>=0 && tok_to_double(buf,&tok[t],&d)) atomic_store(&C->filt.cutoff,(float)fmaxf(20.f,(float)d));
            t = obj_get(buf,tok,it,"q");      if (t>=0 && tok_to_double(buf,&tok[t],&d)) atomic_store(&C->filt.q,(float)fmaxf(0.1f,(float)d));
        }
    }

    // slots[]
    int sarr = obj_get(buf,tok,0,"slots");
    if (sarr>=0 && tok[sarr].type==JSMN_ARRAY){
        int it=0;
        while (array_foreach(tok, sarr, &it)){
            if (tok[it].type!=JSMN_OBJECT){ it = tok_next(tok,it); continue; }
            int t, index=0;
            t = obj_get(buf,tok,it,"index"); if (t<0 || !tok_to_int(buf,&tok[t],&index)) { it=tok_next(tok,it); continue; }
            if (index<1 || index>NUM_SLOTS){ it=tok_next(tok,it); continue; }
            SampleSlot* S = &G.slots[index-1];

            int ch1, b; double d;
            t = obj_get(buf,tok,it,"channel");    if (t>=0 && tok_to_int(buf,&tok[t],&ch1)) atomic_store(&S->assignedCh, clampi(ch1-1,0,NUM_CHANNELS-1));
            t = obj_get(buf,tok,it,"gain");       if (t>=0 && tok_to_double(buf,&tok[t],&d)) atomic_store(&S->gain,(float)clampf((float)d,0.f,10.f));
            t = obj_get(buf,tok,it,"path");       if (t>=0 && tok[t].type==JSMN_STRING){ int len=tok[t].end-tok[t].start; char* path=(char*)malloc((size_t)len+1); memcpy(path,buf+tok[t].start,(size_t)len); path[len]='\0'; (void)slot_load_path(S,path,G.sr); free(path); }
            t = obj_get(buf,tok,it,"autotrigger");if (t>=0 && tok_to_bool(buf,&tok[t],&b) && b){ atomic_store(&S->playing,1); S->pos=0; }
        }
    }

    // voices[]
    int varr = obj_get(buf,tok,0,"voices");
    if (varr>=0 && tok[varr].type==JSMN_ARRAY){
        int it=0;
        while (array_foreach(tok, varr, &it)){
            if (tok[it].type!=JSMN_OBJECT){ it = tok_next(tok,it); continue; }
            int t, index=0;
            t = obj_get(buf,tok,it,"index"); if (t<0 || !tok_to_int(buf,&tok[t],&index)) { it=tok_next(tok,it); continue; }
            if (index<1 || index>NUM_VOICES){ it=tok_next(tok,it); continue; }
            Voice* V = &G.voices[index-1];

            int bi, vi; double d;
            t = obj_get(buf,tok,it,"on");        if (t>=0 && tok_to_bool(buf,&tok[t],&bi)) atomic_store(&V->on, bi?1:0);
            t = obj_get(buf,tok,it,"wave");
            if (t>=0){
                if (tok[t].type==JSMN_STRING){
                    int len = tok[t].end - tok[t].start; char tmp[16]; if (len>(int)sizeof(tmp)-1) len=sizeof(tmp)-1; memcpy(tmp,buf+tok[t].start,(size_t)len); tmp[len]='\0';
                    atomic_store(&V->wave, wave_from_string(tmp));
                } else if (tok_to_int(buf,&tok[t],&vi)) {
                    atomic_store(&V->wave, vi?W_PULSE:W_SINE);
                }
            }
            t = obj_get(buf,tok,it,"freq");      if (t>=0 && tok_to_double(buf,&tok[t],&d)) atomic_store(&V->freq, fmaxf(1.f,(float)d));
            t = obj_get(buf,tok,it,"gain");      if (t>=0 && tok_to_double(buf,&tok[t],&d)) atomic_store(&V->gain, (float)clampf((float)d,0.f,2.f));
            t = obj_get(buf,tok,it,"channel");   if (t>=0 && tok_to_int(buf,&tok[t],&vi)) atomic_store(&V->assignedCh, clampi(vi-1,0,NUM_CHANNELS-1));
            t = obj_get(buf,tok,it,"tau_a");     if (t>=0 && tok_to_double(buf,&tok[t],&d)) atomic_store(&V->tauA, (float)fmaxf(1e-4f,(float)d));
            t = obj_get(buf,tok,it,"tau_b");     if (t>=0 && tok_to_double(buf,&tok[t],&d)) atomic_store(&V->tauB, (float)fmaxf(1e-4f,(float)d));
            t = obj_get(buf,tok,it,"duty_bias"); if (t>=0 && tok_to_double(buf,&tok[t],&d)) atomic_store(&V->dutyBias,(float)clampf((float)d,0.01f,0.99f));
            t = obj_get(buf,tok,it,"spikes");    if (t>=0 && tok_to_int(buf,&tok[t],&vi) && vi>0) atomic_fetch_add(&V->spikes, vi);
        }
    }

    free(tok); free(buf); return 0;
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
    uint32_t sr=ENGINE_SR_DEFAULT, frames=ENGINE_FRAMES_DEF;
    int osc_port=9000;          // must be set by JSON to override default
    float master_gain = 0.8f;
    const char* cfgpath = getenv("ENGINE_CONFIG");

    for (int i=1;i<argc;i++){
        if (!strcmp(argv[i],"--config") && i+1<argc) cfgpath=argv[++i];
        else if (!strcmp(argv[i],"--sr") && i+1<argc) sr=(uint32_t)atoi(argv[++i]);
        else if (!strcmp(argv[i],"--frames") && i+1<argc) frames=(uint32_t)atoi(argv[++i]);
        // OSC port is intentionally read from JSON only.
    }

    if (cfgpath){
        (void)load_config_json_engine(cfgpath, &sr, &frames, &osc_port, &master_gain);
    }

    if (engine_init(&G, sr, frames)!=0){ fprintf(stderr,"engine init failed\n"); return 1; }
    atomic_store(&G.masterGain, master_gain);

    if (cfgpath){
        (void)load_config_json_apply(cfgpath, G.sr);
    }

    osc_srv srv; if (osc_start(&srv, osc_port)!=0){ fprintf(stderr,"OSC start failed (port %d)\n", osc_port); engine_uninit(&G); return 2; }
    if (ma_device_start(&G.device) != MA_SUCCESS){ fprintf(stderr,"audio start failed\n"); osc_stop(&srv); engine_uninit(&G); return 3; }

    fprintf(stderr,"Engine running: sr=%u frames=%u OSC udp/%d\n", G.sr, G.framesPerBuffer, osc_port);
    for(;;){ pause(); }

    ma_device_stop(&G.device);
    osc_stop(&srv);
    engine_uninit(&G);
    return 0;
}
