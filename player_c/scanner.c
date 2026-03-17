/* scanner.c - Recursive media file scanner */

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

static void scan_recurse(const char *dir, const char *base,
                         media_list_t *out) {
    DIR *d = opendir(dir);
    if (!d) return;

    struct dirent *ent;
    while ((ent = readdir(d)) != NULL && out->count < MAX_FILES) {
        if (ent->d_name[0] == '.') continue;

        char fullpath[MAX_PATH_LEN];
        snprintf(fullpath, sizeof(fullpath), "%s/%s", dir, ent->d_name);

        struct stat st;
        if (stat(fullpath, &st) != 0) continue;

        if (S_ISDIR(st.st_mode)) {
            scan_recurse(fullpath, base, out);
        } else if (S_ISREG(st.st_mode)) {
            const char *ext = get_ext(ent->d_name);
            if (!is_media_ext(ext)) continue;

            media_file_t *f = &out->files[out->count];
            snprintf(f->path, MAX_PATH_LEN, "%s", fullpath);
            snprintf(f->name, MAX_NAME_LEN, "%s", ent->d_name);

            /* Lowercase extension */
            size_t elen = strlen(ext);
            if (elen >= sizeof(f->ext)) elen = sizeof(f->ext) - 1;
            for (size_t i = 0; i < elen; i++)
                f->ext[i] = (char)tolower((unsigned char)ext[i]);
            f->ext[elen] = '\0';

            /* Relative parent: strip base prefix */
            const char *rel = fullpath + strlen(base);
            if (*rel == '/') rel++;
            /* Find last slash to get parent */
            const char *last_slash = strrchr(rel, '/');
            if (last_slash) {
                size_t plen = (size_t)(last_slash - rel);
                if (plen >= MAX_NAME_LEN) plen = MAX_NAME_LEN - 1;
                memcpy(f->parent, rel, plen);
                f->parent[plen] = '\0';
            } else {
                f->parent[0] = '\0';
            }

            out->count++;
        }
    }
    closedir(d);
}

static int cmp_by_path(const void *a, const void *b) {
    return strcmp(((const media_file_t *)a)->path,
                  ((const media_file_t *)b)->path);
}

static int cmp_by_name(const void *a, const void *b) {
    return strcasecmp(((const media_file_t *)a)->name,
                      ((const media_file_t *)b)->name);
}

int scan_directory(const char *dir, media_list_t *out) {
    out->count = 0;
    scan_recurse(dir, dir, out);
    sort_by_path(out);
    return out->count;
}

void sort_by_name(media_list_t *list) {
    qsort(list->files, (size_t)list->count, sizeof(media_file_t), cmp_by_name);
}

void sort_by_path(media_list_t *list) {
    qsort(list->files, (size_t)list->count, sizeof(media_file_t), cmp_by_path);
}
