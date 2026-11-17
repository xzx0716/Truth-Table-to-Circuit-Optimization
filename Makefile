CXX ?= g++
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra -Wpedantic
SOURCES := src/main.cpp $(wildcard src/optimization/*.cpp)
all: build/solver
build/solver: $(SOURCES) $(wildcard include/ttc/*.hpp)
	mkdir -p build
	$(CXX) $(CXXFLAGS) -Iinclude $(SOURCES) -o $@
test: build/solver
	python3 tests/verify_solver.py build/solver --no-stats
clean:
	rm -f build/solver
.PHONY: all test clean
