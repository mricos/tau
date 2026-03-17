// envelope.h - Double-tau exponential envelope and LFO for tau-engine
// Add to tau-engine.c after includes

#ifndef TAU_ENVELOPE_H
#define TAU_ENVELOPE_H

//==============================================================================
// ENVELOPE STATE MACHINE
//==============================================================================
// Double-tau exponential envelope eliminates clicks from instant on/off
// Attack:  env(t) = target * (1 - e^(-t/tau1))
// Release: env(t) = level  * e^(-t/tau2)

typedef enum {
    ENV_OFF = 0,      // Silent, gain = 0
    ENV_ATTACK,       // Rising from 0 toward target
    ENV_SUSTAIN,      // Holding at target level
    ENV_RELEASE       // Decaying toward 0
} EnvState;

typedef struct {
    _Atomic int state;         // EnvState
    _Atomic float tau1;        // Attack time constant (seconds)
    _Atomic float tau2;        // Release time constant (seconds)
    _Atomic float target;      // Target gain level
    float current;             // Current envelope value (0-1)
    float sr;                  // Sample rate
} Envelope;

static inline void env_init(Envelope* e, float sr) {
    atomic_store(&e->state, ENV_OFF);
    atomic_store(&e->tau1, 0.005f);   // 5ms attack (snappy, no click)
    atomic_store(&e->tau2, 0.050f);   // 50ms release (natural decay)
    atomic_store(&e->target, 1.0f);
    e->current = 0.0f;
    e->sr = sr;
}

// Trigger envelope: start attack phase
static inline void env_trigger(Envelope* e) {
    atomic_store(&e->state, ENV_ATTACK);
}

// Release envelope: start decay phase
static inline void env_release(Envelope* e) {
    atomic_store(&e->state, ENV_RELEASE);
}

// Process one sample, return envelope value (0 to target)
static inline float env_tick(Envelope* e) {
    int state = atomic_load(&e->state);
    float target = atomic_load(&e->target);

    switch (state) {
        case ENV_OFF:
            e->current = 0.0f;
            break;

        case ENV_ATTACK: {
            float tau1 = fmaxf(1e-5f, atomic_load(&e->tau1));
            float alpha = 1.0f - expf(-1.0f / (tau1 * e->sr));
            e->current += alpha * (target - e->current);
            // Transition to sustain when close enough
            if (e->current >= target * 0.999f) {
                e->current = target;
                atomic_store(&e->state, ENV_SUSTAIN);
            }
            break;
        }

        case ENV_SUSTAIN:
            e->current = target;
            break;

        case ENV_RELEASE: {
            float tau2 = fmaxf(1e-5f, atomic_load(&e->tau2));
            float decay = expf(-1.0f / (tau2 * e->sr));
            e->current *= decay;
            // Transition to off when quiet enough
            if (e->current < 0.0001f) {
                e->current = 0.0f;
                atomic_store(&e->state, ENV_OFF);
            }
            break;
        }
    }

    return e->current;
}

// Check if envelope is active (not OFF)
static inline int env_is_active(Envelope* e) {
    return atomic_load(&e->state) != ENV_OFF;
}

//==============================================================================
// LFO - Low Frequency Oscillator
//==============================================================================
// Modulates parameters with sine, triangle, square, or S&H waveforms

typedef enum {
    LFO_OFF = 0,
    LFO_SINE,
    LFO_TRIANGLE,
    LFO_SQUARE,
    LFO_SAW,
    LFO_RANDOM    // Sample & Hold
} LFOWave;

typedef enum {
    LFO_TARGET_NONE = 0,
    LFO_TARGET_FREQ,
    LFO_TARGET_GAIN,
    LFO_TARGET_PAN,
    LFO_TARGET_CUTOFF,
    LFO_TARGET_DUTY
} LFOTarget;

typedef struct {
    _Atomic int wave;          // LFOWave
    _Atomic int target;        // LFOTarget
    _Atomic float rate;        // Hz
    _Atomic float depth;       // Modulation amount (interpretation depends on target)
    float phase;               // 0-1
    float sr;
    float held_value;          // For S&H mode
} LFO;

static inline void lfo_init(LFO* l, float sr) {
    atomic_store(&l->wave, LFO_OFF);
    atomic_store(&l->target, LFO_TARGET_NONE);
    atomic_store(&l->rate, 1.0f);
    atomic_store(&l->depth, 0.0f);
    l->phase = 0.0f;
    l->sr = sr;
    l->held_value = 0.0f;
}

// Process one sample, return modulation value (-1 to +1) scaled by depth
static inline float lfo_tick(LFO* l) {
    int wave = atomic_load(&l->wave);
    if (wave == LFO_OFF) return 0.0f;

    float rate = fmaxf(0.001f, atomic_load(&l->rate));
    float depth = atomic_load(&l->depth);

    // Advance phase
    float prev_phase = l->phase;
    l->phase += rate / l->sr;
    if (l->phase >= 1.0f) l->phase -= 1.0f;

    float value = 0.0f;
    switch (wave) {
        case LFO_SINE:
            value = sinf(TWO_PI * l->phase);
            break;

        case LFO_TRIANGLE:
            value = 4.0f * fabsf(l->phase - 0.5f) - 1.0f;
            break;

        case LFO_SQUARE:
            value = (l->phase < 0.5f) ? 1.0f : -1.0f;
            break;

        case LFO_SAW:
            value = 2.0f * l->phase - 1.0f;
            break;

        case LFO_RANDOM:
            // Sample new value at start of each cycle
            if (l->phase < prev_phase) {
                l->held_value = 2.0f * ((float)rand() / (float)RAND_MAX) - 1.0f;
            }
            value = l->held_value;
            break;
    }

    return value * depth;
}

//==============================================================================
// ENHANCED VOICE STRUCTURE
//==============================================================================
// Replace the existing Voice struct in tau-engine.c

typedef struct {
    // Existing fields
    _Atomic int on;
    _Atomic int wave;            // W_SINE or W_PULSE
    _Atomic float freq;
    _Atomic float gain;          // Target gain (envelope modulates this)
    _Atomic int assignedCh;

    // LIF modulation for pulse width (existing)
    _Atomic float tauA;
    _Atomic float tauB;
    _Atomic float dutyBias;
    _Atomic int spikes;
    float Astate, Bstate;

    // Oscillator state
    float phase;
    float sr;

    // NEW: Amplitude envelope
    Envelope env;

    // NEW: Per-voice filter
    SVF filt;

    // NEW: LFOs (up to 2 per voice)
    LFO lfo1;
    LFO lfo2;
} VoiceEnhanced;

static void voice_enhanced_init(VoiceEnhanced* v, float sr) {
    memset(v, 0, sizeof(*v));
    v->sr = sr;
    atomic_store(&v->on, 0);
    atomic_store(&v->wave, W_SINE);
    atomic_store(&v->freq, 220.0f);
    atomic_store(&v->gain, 0.5f);
    atomic_store(&v->assignedCh, 0);
    atomic_store(&v->tauA, 0.005f);
    atomic_store(&v->tauB, 0.020f);
    atomic_store(&v->dutyBias, 0.5f);
    atomic_store(&v->spikes, 0);

    // Initialize new components
    env_init(&v->env, sr);
    svf_init(&v->filt, sr);
    lfo_init(&v->lfo1, sr);
    lfo_init(&v->lfo2, sr);
}

static inline float voice_enhanced_tick(VoiceEnhanced* v) {
    // Check if voice should produce sound
    int on = atomic_load(&v->on);
    int env_active = env_is_active(&v->env);

    if (!on && !env_active) return 0.0f;

    // Process spikes (LIF for pulse width modulation)
    int s = atomic_exchange(&v->spikes, 0);
    if (s > 0) { v->Astate += (float)s; v->Bstate += (float)s; }

    // Get base parameters
    float base_freq = fmaxf(1.0f, atomic_load(&v->freq));
    float base_gain = atomic_load(&v->gain);
    int wave = atomic_load(&v->wave);
    float ta = fmaxf(1e-4f, atomic_load(&v->tauA));
    float tb = fmaxf(1e-4f, atomic_load(&v->tauB));

    // Apply LFO modulation
    float lfo1_val = lfo_tick(&v->lfo1);
    float lfo2_val = lfo_tick(&v->lfo2);

    float freq = base_freq;
    float gain_mod = 1.0f;
    float cutoff_mod = 0.0f;
    float duty_mod = 0.0f;

    // Route LFO1
    switch (atomic_load(&v->lfo1.target)) {
        case LFO_TARGET_FREQ:   freq *= powf(2.0f, lfo1_val / 12.0f); break;  // Semitones
        case LFO_TARGET_GAIN:   gain_mod *= (1.0f + lfo1_val); break;
        case LFO_TARGET_CUTOFF: cutoff_mod += lfo1_val; break;
        case LFO_TARGET_DUTY:   duty_mod += lfo1_val * 0.25f; break;
        default: break;
    }

    // Route LFO2
    switch (atomic_load(&v->lfo2.target)) {
        case LFO_TARGET_FREQ:   freq *= powf(2.0f, lfo2_val / 12.0f); break;
        case LFO_TARGET_GAIN:   gain_mod *= (1.0f + lfo2_val); break;
        case LFO_TARGET_CUTOFF: cutoff_mod += lfo2_val; break;
        case LFO_TARGET_DUTY:   duty_mod += lfo2_val * 0.25f; break;
        default: break;
    }

    // LIF double-exponential for pulse width
    float da = expf(-1.0f / (ta * v->sr));
    float db = expf(-1.0f / (tb * v->sr));
    v->Astate *= da;
    v->Bstate *= db;
    float k = v->Astate - v->Bstate;
    float duty = clampf(atomic_load(&v->dutyBias) + 0.25f * k + duty_mod, 0.01f, 0.99f);

    // Oscillator
    v->phase += freq / v->sr;
    if (v->phase >= 1.0f) v->phase -= 1.0f;

    float osc = (wave == W_SINE) ? sinf(TWO_PI * v->phase) : ((v->phase < duty) ? 1.0f : -1.0f);

    // Apply envelope
    float env_val = env_tick(&v->env);

    // Apply filter (if enabled)
    float filtered = svf_process(&v->filt, osc);

    // Final output: oscillator * envelope * gain * lfo_gain_mod
    return filtered * env_val * base_gain * clampf(gain_mod, 0.0f, 2.0f);
}

//==============================================================================
// NEW SOCKET COMMANDS
//==============================================================================
// Add these to the cmd_parse function in tau-engine.c

/*
VOICE n ENV tau1 tau2       Set envelope time constants
VOICE n TRIG                Trigger attack (starts playing)
VOICE n REL                 Release (starts decay)
VOICE n FILT type cutoff q  Set voice filter (LP/HP/BP/OFF, freq, Q)
VOICE n LFO1 wave rate depth target   Configure LFO1
VOICE n LFO2 wave rate depth target   Configure LFO2

Example usage:
  VOICE 1 ENV 0.01 0.1      # 10ms attack, 100ms release
  VOICE 1 FREQ 440
  VOICE 1 GAIN 0.5
  VOICE 1 TRIG              # Start sound with envelope
  ... later ...
  VOICE 1 REL               # Release (fade out)

  VOICE 2 FILT LP 800 0.7   # Lowpass at 800Hz
  VOICE 2 LFO1 SINE 5 0.3 FREQ   # 5Hz vibrato, 0.3 semitones depth
  VOICE 2 LFO2 TRI 0.2 500 CUTOFF # Slow filter sweep
*/

// Command parsing helper (add to cmd_parse in tau-engine.c)
/*
if (strcmp(tokens[2], "ENV") == 0) {
    if (ntok < 5) {
        snprintf(response, resp_size, "ERROR Missing tau1/tau2\n");
        return;
    }
    float tau1 = strtof(tokens[3], NULL);
    float tau2 = strtof(tokens[4], NULL);
    atomic_store(&V->env.tau1, fmaxf(0.001f, tau1));
    atomic_store(&V->env.tau2, fmaxf(0.001f, tau2));
    snprintf(response, resp_size, "OK VOICE %d ENV %.3f %.3f\n", vi, tau1, tau2);
    return;
}

if (strcmp(tokens[2], "TRIG") == 0) {
    atomic_store(&V->on, 1);
    env_trigger(&V->env);
    snprintf(response, resp_size, "OK VOICE %d TRIG\n", vi);
    return;
}

if (strcmp(tokens[2], "REL") == 0) {
    env_release(&V->env);
    // Note: don't set V->on = 0 here, let envelope finish naturally
    snprintf(response, resp_size, "OK VOICE %d REL\n", vi);
    return;
}

if (strcmp(tokens[2], "FILT") == 0) {
    if (ntok < 6) {
        snprintf(response, resp_size, "ERROR FILT needs type cutoff q\n");
        return;
    }
    int type = F_OFF;
    if (strcasecmp(tokens[3], "LP") == 0) type = F_LP;
    else if (strcasecmp(tokens[3], "HP") == 0) type = F_HP;
    else if (strcasecmp(tokens[3], "BP") == 0) type = F_BP;
    float cutoff = strtof(tokens[4], NULL);
    float q = strtof(tokens[5], NULL);
    atomic_store(&V->filt.type, type);
    atomic_store(&V->filt.cutoff, cutoff);
    atomic_store(&V->filt.q, q);
    snprintf(response, resp_size, "OK VOICE %d FILT %s %.1f %.2f\n", vi, tokens[3], cutoff, q);
    return;
}

if (strcmp(tokens[2], "LFO1") == 0 || strcmp(tokens[2], "LFO2") == 0) {
    LFO* lfo = (tokens[2][3] == '1') ? &V->lfo1 : &V->lfo2;
    if (ntok < 7) {
        snprintf(response, resp_size, "ERROR LFO needs wave rate depth target\n");
        return;
    }
    int wave = LFO_OFF;
    if (strcasecmp(tokens[3], "SINE") == 0) wave = LFO_SINE;
    else if (strcasecmp(tokens[3], "TRI") == 0) wave = LFO_TRIANGLE;
    else if (strcasecmp(tokens[3], "SQR") == 0) wave = LFO_SQUARE;
    else if (strcasecmp(tokens[3], "SAW") == 0) wave = LFO_SAW;
    else if (strcasecmp(tokens[3], "RND") == 0) wave = LFO_RANDOM;

    float rate = strtof(tokens[4], NULL);
    float depth = strtof(tokens[5], NULL);

    int target = LFO_TARGET_NONE;
    if (strcasecmp(tokens[6], "FREQ") == 0) target = LFO_TARGET_FREQ;
    else if (strcasecmp(tokens[6], "GAIN") == 0) target = LFO_TARGET_GAIN;
    else if (strcasecmp(tokens[6], "PAN") == 0) target = LFO_TARGET_PAN;
    else if (strcasecmp(tokens[6], "CUTOFF") == 0) target = LFO_TARGET_CUTOFF;
    else if (strcasecmp(tokens[6], "DUTY") == 0) target = LFO_TARGET_DUTY;

    atomic_store(&lfo->wave, wave);
    atomic_store(&lfo->rate, rate);
    atomic_store(&lfo->depth, depth);
    atomic_store(&lfo->target, target);

    snprintf(response, resp_size, "OK VOICE %d %s %s %.2f %.2f %s\n",
             vi, tokens[2], tokens[3], rate, depth, tokens[6]);
    return;
}
*/

#endif // TAU_ENVELOPE_H
