CC     = gcc
CFLAGS = -Wall -Wextra -std=c11 -g -Isrc
SRC    = $(wildcard src/*.c)
OBJ    = $(SRC:src/%.c=build/%.o)
TARGET = axelcc

all: $(TARGET)

$(TARGET): $(OBJ)
	$(CC) $(CFLAGS) -o $@ $^

build/%.o: src/%.c | build
	$(CC) $(CFLAGS) -c -o $@ $<

build:
	mkdir -p build

clean:
	rm -rf build $(TARGET)

test: $(TARGET)
	./$(TARGET) --tokens examples/relu.axelc

.PHONY: all clean test