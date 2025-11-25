# tau-repl C REPL Makefile

CC = clang
CFLAGS = -Wall -Wextra -O2
LDFLAGS = -lreadline

TARGET = tau-repl
SRC = tau-repl.c

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f $(TARGET)
