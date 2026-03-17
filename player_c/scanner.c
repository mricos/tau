/* scanner.c - Flat directory media file scanner with metadata */

#include "scanner.h"
#include <stdio.h>
#include <dirent.h>
#include <string.h>
#include <strings.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <ctype.h>

static const char *MEDIA_EXTS[] = {
    ".mp3", ".wav", ".flac", ".ogg", ".aac", ".mp4", ".webm", NULL
};

static int is_media_ext(const char *ext) {
    for (int i = 0; MEDIA_EXTS[i]; i++) {
        if (strcasecmp(ext, MEDIA_EXTS[i]) == 0) return 1;
    }
    return 0;
}

static const char *get_ext(const char *name) {
    const char *dot = strrchr(name, '.');
    return dot ? dot : "";
}

/* Probe metadata via ffprobe: duration, artist, album, title */
static void probe_metadata(media_file_t *f) {
    char cmd[2048];
    snprintf(cmd, sizeof(cmd),
        "ffprobe -v quiet -print_format csv=p=0 "
        "-show_entries format=duration "
        "-show_entries format_tags=artist,album,title "
        "'%s' 2>/dev/null", f->path);

    FILE *fp = popen(cmd, "r");
    if (!fp) return;

    char line[1024];
    while (fgets(line, sizeof(line), fp)) {
        /* Remove trailing newline */
        char *nl = strchr(line, '\n');
        if (nl) *nl = '\0';

        /* Duration line is just a number */
        if (line[0] >= '0' && line[0] <= '9') {
            f->duration = (float)atof(line);
        }
        /* Tag lines: key=value */
        char *eq = strchr(line, '=');
        if (eq) {
            *eq = '\0';
            const char *key = line;
            const char *val = eq + 1;
            if (strcasecmp(key, "artist") == 0)
                snprintf(f->artist, MAX_NAME_LEN, "%s", val);
            else if (strcasecmp(key, "album") == 0)
                snprintf(f->album, MAX_NAME_LEN, "%s", val);
            else if (strcasecmp(key, "title") == 0)
                snprintf(f->title, MAX_NAME_LEN, "%s", val);
        }
    }
    pclose(fp);
}

int scan_directory(const char *dir, media_list_t *out) {
    out->count = 0;

    DIR *d = opendir(dir);
    if (!d) return 0;

    struct dirent *ent;
    while ((ent = readdir(d)) != NULL && out->count < MAX_FILES) {
        if (ent->d_name[0] == '.') continue;

        char fullpath[MAX_PATH_LEN];
        snprintf(fullpath, sizeof(fullpath), "%s/%s", dir, ent->d_name);

        struct stat st;
        if (stat(fullpath, &st) != 0) continue;
        if (!S_ISREG(st.st_mode)) continue;

        const char *ext = get_ext(ent->d_name);
        if (!is_media_ext(ext)) continue;

        media_file_t *f = &out->files[out->count];
        memset(f, 0, sizeof(*f));
        snprintf(f->path, MAX_PATH_LEN, "%s", fullpath);
        snprintf(f->name, MAX_NAME_LEN, "%s", ent->d_name);
        f->file_size = (int)st.st_size;

        /* Lowercase extension */
        size_t elen = strlen(ext);
        if (elen >= sizeof(f->ext)) elen = sizeof(f->ext) - 1;
        for (size_t i = 0; i < elen; i++)
            f->ext[i] = (char)tolower((unsigned char)ext[i]);
        f->ext[elen] = '\0';

        probe_metadata(f);
        out->count++;
    }
    closedir(d);

    sort_by_name(out);
    return out->count;
}

/* ── Sort functions ── */

static int cmp_by_path(const void *a, const void *b) {
    return strcmp(((const media_file_t *)a)->path,
                  ((const media_file_t *)b)->path);
}

static int cmp_by_name(const void *a, const void *b) {
    return strcasecmp(((const media_file_t *)a)->name,
                      ((const media_file_t *)b)->name);
}

static int cmp_by_artist(const void *a, const void *b) {
    const media_file_t *fa = a, *fb = b;
    int r = strcasecmp(fa->artist, fb->artist);
    if (r != 0) return r;
    return strcasecmp(fa->album, fb->album);
}

static int cmp_by_album(const void *a, const void *b) {
    const media_file_t *fa = a, *fb = b;
    int r = strcasecmp(fa->album, fb->album);
    if (r != 0) return r;
    return strcasecmp(fa->name, fb->name);
}

static int cmp_by_duration(const void *a, const void *b) {
    float da = ((const media_file_t *)a)->duration;
    float db = ((const media_file_t *)b)->duration;
    if (da < db) return -1;
    if (da > db) return 1;
    return 0;
}

void sort_by_name(media_list_t *list) {
    qsort(list->files, (size_t)list->count, sizeof(media_file_t), cmp_by_name);
}

void sort_by_path(media_list_t *list) {
    qsort(list->files, (size_t)list->count, sizeof(media_file_t), cmp_by_path);
}

void sort_by_artist(media_list_t *list) {
    qsort(list->files, (size_t)list->count, sizeof(media_file_t), cmp_by_artist);
}

void sort_by_album(media_list_t *list) {
    qsort(list->files, (size_t)list->count, sizeof(media_file_t), cmp_by_album);
}

void sort_by_duration(media_list_t *list) {
    qsort(list->files, (size_t)list->count, sizeof(media_file_t), cmp_by_duration);
}

const char *media_display_label(const media_file_t *f) {
    return f->title[0] ? f->title : f->name;
}
