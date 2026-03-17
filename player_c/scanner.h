/* scanner.h - Recursive media file scanner */

#ifndef TAU_SCANNER_H
#define TAU_SCANNER_H

#include <stddef.h>

#define MAX_PATH_LEN   1024
#define MAX_NAME_LEN    256
#define MAX_FILES      4096

typedef struct {
    char path[MAX_PATH_LEN];      /* full path */
    char name[MAX_NAME_LEN];      /* filename only */
    char parent[MAX_NAME_LEN];    /* relative parent dir (from scan root) */
    char ext[16];                 /* lowercase extension with dot */
} media_file_t;

typedef struct {
    media_file_t files[MAX_FILES];
    int count;
} media_list_t;

/* Scan directory recursively for media files. Sorts by path.
 * Returns number of files found. */
int scan_directory(const char *dir, media_list_t *out);

/* Sort list by filename (case-insensitive). */
void sort_by_name(media_list_t *list);

/* Sort list by full path. */
void sort_by_path(media_list_t *list);

#endif /* TAU_SCANNER_H */
