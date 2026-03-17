/* transport.h - Audio playback via ffplay (tau-engine socket later) */

#ifndef TAU_TRANSPORT_H
#define TAU_TRANSPORT_H

typedef struct {
    int    playing;
    int    paused;
    double position;
    double duration;
    double last_time;   /* monotonic clock */
    float  volume;      /* 0.0 - 1.0 */
    int    ffplay_pid;  /* -1 if not running */
    char   loaded_path[1024];
    char   backend[16]; /* "ffplay" or "none" */
} transport_t;

/* Initialize transport. */
void transport_init(transport_t *t);

/* Load a file. Gets duration via ffprobe. */
int transport_load(transport_t *t, const char *path);

/* Play / pause / stop / toggle. */
void transport_play(transport_t *t);
void transport_pause(transport_t *t);
void transport_stop(transport_t *t);
void transport_toggle(transport_t *t);

/* Seek absolute / relative (seconds). */
void transport_seek(transport_t *t, double pos);
void transport_seek_rel(transport_t *t, double delta);

/* Volume 0.0 - 1.0. */
void transport_set_volume(transport_t *t, float vol);

/* Call every frame. Returns 1 if track ended (for auto-advance). */
int transport_update(transport_t *t);

/* Clean up child processes. */
void transport_cleanup(transport_t *t);

#endif /* TAU_TRANSPORT_H */
