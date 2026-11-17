CXX ?= g++
CXXFLAGS ?= -O2 -std=c++17 -Wall -Wextra -Wpedantic
SOURCES := src/main.cpp $(wildcard src/optimization/*.cpp)
all: build/solver
build/solver: $(SOURCES) $(wildcard include/ttc/*.hpp)
	mkdir -p build
	$(CXX) $(CXXFLAGS) -Iinclude $(SOURCES) -o $@
test: build/solver
	python3 tests/verify_solver.py build/solver --no-stats
unit: build/solver
	$(CXX) $(CXXFLAGS) -Iinclude tests/test_local_rewrite.cpp src/optimization/budget.cpp src/optimization/local_rewrite.cpp -o build/test_local
	./build/test_local
export:
	python3 tools/export_submission.py --output dist/solver.cpp
clean:
	rm -f build/solver
.PHONY: all test unit export clean
