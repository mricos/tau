/* scanner.h - Flat directory media file scanner with metadata */

#ifndef TAU_SCANNER_H
#define TAU_SCANNER_H

#include <stddef.h>

#define MAX_PATH_LEN   1024
#define MAX_NAME_LEN    256
#define MAX_FILES      4096

typedef struct {
    char path[MAX_PATH_LEN];      /* full path */
    char name[MAX_NAME_LEN];      /* filename only */
    char ext[16];                 /* lowercase extension with dot */
    /* Metadata (populated via ffprobe) */
    char artist[MAX_NAME_LEN];
    char album[MAX_NAME_LEN];
    char title[MAX_NAME_LEN];
    float duration;               /* seconds, 0 if unknown */
    int file_size;
} media_file_t;

typedef struct {
    media_file_t files[MAX_FILES];
    int count;
} media_list_t;

/* Scan single directory (non-recursive) for media files. Sorts by name.
 * Returns number of files found. */
int scan_directory(const char *dir, media_list_t *out);

/* Sort functions */
void sort_by_name(media_list_t *list);
void sort_by_path(media_list_t *list);
void sort_by_artist(media_list_t *list);
void sort_by_album(media_list_t *list);
void sort_by_duration(media_list_t *list);

/* Display label: title if available, else filename */
const char *media_display_label(const media_file_t *f);

#endif /* TAU_SCANNER_H */
