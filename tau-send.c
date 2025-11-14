// tau-send.c - Send commands to tau via Unix datagram socket
// Build: gcc -o tau-send tau-send.c
// Usage: tau-send "VOICE 1 ON"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>

int main(int argc, char** argv){
    if (argc < 2){
        fprintf(stderr, "Usage: %s <command>\n", argv[0]);
        fprintf(stderr, "Example: %s \"STATUS\"\n", argv[0]);
        return 1;
    }

    // Build command from all args
    char cmd[4096] = "";
    for (int i = 1; i < argc; i++){
        if (i > 1) strcat(cmd, " ");
        strcat(cmd, argv[i]);
    }

    // Get socket path
    const char* socket_path = getenv("TAU_SOCKET");
    if (!socket_path){
        const char* home = getenv("HOME");
        if (!home) home = "/tmp";
        static char default_path[512];
        snprintf(default_path, sizeof(default_path), "%s/tau/runtime/tau.sock", home);
        socket_path = default_path;
    }

    // Create client socket
    int sock = socket(AF_UNIX, SOCK_DGRAM, 0);
    if (sock < 0){
        perror("socket");
        return 2;
    }

    // Bind client to temp socket (required for datagram)
    struct sockaddr_un client_addr;
    memset(&client_addr, 0, sizeof(client_addr));
    client_addr.sun_family = AF_UNIX;
    snprintf(client_addr.sun_path, sizeof(client_addr.sun_path),
             "/tmp/tau-client-%d.sock", getpid());
    unlink(client_addr.sun_path);

    if (bind(sock, (struct sockaddr*)&client_addr, sizeof(client_addr)) < 0){
        perror("bind");
        close(sock);
        return 3;
    }

    // Server address
    struct sockaddr_un server_addr;
    memset(&server_addr, 0, sizeof(server_addr));
    server_addr.sun_family = AF_UNIX;
    strncpy(server_addr.sun_path, socket_path, sizeof(server_addr.sun_path)-1);

    // Send command
    ssize_t n = sendto(sock, cmd, strlen(cmd), 0,
                       (struct sockaddr*)&server_addr, sizeof(server_addr));
    if (n < 0){
        perror("sendto");
        close(sock);
        unlink(client_addr.sun_path);
        return 4;
    }

    // Receive response
    char response[4096];
    struct sockaddr_un from_addr;
    socklen_t from_len = sizeof(from_addr);

    n = recvfrom(sock, response, sizeof(response)-1, 0,
                 (struct sockaddr*)&from_addr, &from_len);
    if (n > 0){
        response[n] = '\0';
        printf("%s", response);
    }

    // Cleanup
    close(sock);
    unlink(client_addr.sun_path);

    return 0;
}
