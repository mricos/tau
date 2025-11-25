/*
 * tau-repl.c - C REPL for tau-engine
 *
 * Placeholder implementation.
 * See repl_py/ for full Python implementation.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <readline/readline.h>
#include <readline/history.h>

#define SOCKET_PATH "~/tau/runtime/tau.sock"
#define MAX_BUF 4096

int main(int argc, char *argv[]) {
    (void)argc;
    (void)argv;

    printf("tau-repl (C) - Not yet implemented\n");
    printf("Use Python REPL: tau\n");

    return 0;
}
