/* transport.c - Audio playback via ffplay */

#include "transport.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <unistd.h>
#include <sys/wait.h>
#include <time.h>

static double mono_time(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

static double get_duration(const char *path) {
    /* Try ffprobe */
    char cmd[2048];
    snprintf(cmd, sizeof(cmd),
        "ffprobe -v quiet -show_entries format=duration "
        "-of default=noprint_wrappers=1:nokey=1 '%s' 2>/dev/null", path);
    FILE *fp = popen(cmd, "r");
    if (!fp) return 0.0;
    char buf[64];
    double dur = 0.0;
    if (fgets(buf, sizeof(buf), fp)) {
        dur = atof(buf);
    }
    pclose(fp);
    return dur;
}

static void kill_ffplay(transport_t *t) {
    if (t->ffplay_pid > 0) {
        kill(t->ffplay_pid, SIGTERM);
        int status;
        /* Non-blocking wait, then force kill */
        usleep(100000);
        if (waitpid(t->ffplay_pid, &status, WNOHANG) == 0) {
            kill(t->ffplay_pid, SIGKILL);
            waitpid(t->ffplay_pid, &status, 0);
        }
        t->ffplay_pid = -1;
    }
}

static void start_ffplay(transport_t *t, double start_pos) {
    kill_ffplay(t);

    pid_t pid = fork();
    if (pid == 0) {
        /* Child: redirect all output to /dev/null */
        freopen("/dev/null", "r", stdin);
        freopen("/dev/null", "w", stdout);
        freopen("/dev/null", "w", stderr);

        char vol_str[16];
        snprintf(vol_str, sizeof(vol_str), "%d", (int)(t->volume * 100));

        if (start_pos > 0.1) {
            char ss_str[32];
            snprintf(ss_str, sizeof(ss_str), "%.2f", start_pos);
            execlp("ffplay", "ffplay",
                   "-nodisp", "-autoexit", "-loglevel", "quiet",
                   "-volume", vol_str, "-ss", ss_str,
                   t->loaded_path, NULL);
        } else {
            execlp("ffplay", "ffplay",
                   "-nodisp", "-autoexit", "-loglevel", "quiet",
                   "-volume", vol_str,
                   t->loaded_path, NULL);
        }
        _exit(127);
    } else if (pid > 0) {
        t->ffplay_pid = pid;
    }
}

void transport_init(transport_t *t) {
    memset(t, 0, sizeof(*t));
    t->volume = 0.8f;
    t->ffplay_pid = -1;
    strncpy(t->backend, "none", sizeof(t->backend));
}

int transport_load(transport_t *t, const char *path) {
    transport_stop(t);
    strncpy(t->loaded_path, path, sizeof(t->loaded_path) - 1);
    t->loaded_path[sizeof(t->loaded_path) - 1] = '\0';
    t->position = 0.0;
    t->duration = get_duration(path);
    strncpy(t->backend, "ffplay", sizeof(t->backend));
    return 1;
}

void transport_play(transport_t *t) {
    if (!t->loaded_path[0]) return;
    if (t->playing) return;
    t->playing = 1;
    t->paused = 0;
    t->last_time = mono_time();
    start_ffplay(t, t->position);
}

void transport_pause(transport_t *t) {
    if (!t->playing) return;
    t->playing = 0;
    t->paused = 1;
    kill_ffplay(t);
}

void transport_stop(transport_t *t) {
    t->playing = 0;
    t->paused = 0;
    t->position = 0.0;
    kill_ffplay(t);
}

void transport_toggle(transport_t *t) {
    if (t->playing) transport_pause(t);
    else            transport_play(t);
}

void transport_seek(transport_t *t, double pos) {
    if (t->duration > 0.0) {
        if (pos < 0.0) pos = 0.0;
        if (pos > t->duration) pos = t->duration;
    } else {
        if (pos < 0.0) pos = 0.0;
    }
    t->position = pos;
    t->last_time = mono_time();
    if (t->playing) start_ffplay(t, pos);
}

void transport_seek_rel(transport_t *t, double delta) {
    transport_seek(t, t->position + delta);
}

void transport_set_volume(transport_t *t, float vol) {
    if (vol < 0.0f) vol = 0.0f;
    if (vol > 1.0f) vol = 1.0f;
    t->volume = vol;
    /* ffplay doesn't support live volume change; takes effect on next play */
}

int transport_update(transport_t *t) {
    if (!t->playing) return 0;

    /* Check if ffplay exited */
    if (t->ffplay_pid > 0) {
        int status;
        pid_t r = waitpid(t->ffplay_pid, &status, WNOHANG);
        if (r > 0) {
            t->ffplay_pid = -1;
            t->playing = 0;
            if (t->duration > 0.0) t->position = t->duration;
            return 1; /* track ended */
        }
    }

    /* Advance wall-clock position */
    double now = mono_time();
    double dt = now - t->last_time;
    t->last_time = now;
    t->position += dt;

    if (t->duration > 0.0 && t->position >= t->duration) {
        t->playing = 0;
        t->position = t->duration;
        kill_ffplay(t);
        return 1;
    }
    return 0;
}

void transport_cleanup(transport_t *t) {
    kill_ffplay(t);
}
