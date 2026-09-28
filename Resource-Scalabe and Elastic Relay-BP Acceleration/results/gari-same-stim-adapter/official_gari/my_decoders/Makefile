# Makefile for HBP Decoder with OpenMP support
# Phase 1 Implementation - Task 1.1: Add OpenMP Support to Build System

# Detect OpenMP-compatible compiler and system
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
    # macOS with Apple clang and libomp
    CC = clang
    HOMEBREW_PREFIX := $(shell brew --prefix 2>/dev/null || echo /opt/homebrew)
    LIBOMP_PATH := $(shell find $(HOMEBREW_PREFIX)/Cellar/libomp -name "libomp.dylib" 2>/dev/null | head -1)
    LIBOMP_INCLUDE := $(shell find $(HOMEBREW_PREFIX)/Cellar/libomp -name "omp.h" -exec dirname {} \; 2>/dev/null | head -1)
    CFLAGS = -O3 -fPIC -Wall -Wextra -Xpreprocessor -fopenmp -I$(LIBOMP_INCLUDE)
    LDFLAGS = -shared $(LIBOMP_PATH)
    OPENMP_LIB = -Xpreprocessor -fopenmp
else
    # Linux or other Unix systems
    ifeq ($(shell which gcc 2>/dev/null),)
        CC = clang
        CFLAGS = -O3 -fPIC -Wall -Wextra -fopenmp
        LDFLAGS = -shared -fopenmp
        OPENMP_LIB = -fopenmp
    else
        CC = gcc
        CFLAGS = -O3 -fPIC -Wall -Wextra -fopenmp
        LDFLAGS = -shared -fopenmp
        OPENMP_LIB = -fopenmp
    endif
endif
TARGET = hbplib_v2.so
SOURCE = hbp_decoder_v2.c

# Default target - build all libraries
all: $(TARGET)

# Build the original shared library with OpenMP support
$(TARGET): $(SOURCE)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $<


# Clean build artifacts
clean:
	rm -f $(TARGET)

# Test compilation with different OpenMP versions
test-openmp:
	@echo "Testing OpenMP compilation with $(CC)..."
	@echo "Compiler flags: $(CFLAGS)"
	@echo "Linker flags: $(LDFLAGS)"
	@$(CC) $(OPENMP_LIB) -dM -E - < /dev/null | grep -i openmp || echo "OpenMP not detected in preprocessor"
	@echo "OpenMP version test completed"

# Install target (copies to parent directory for compatibility)
install: $(TARGET)
	cp $(TARGET) ../$(TARGET)

.PHONY: all clean test-openmp install