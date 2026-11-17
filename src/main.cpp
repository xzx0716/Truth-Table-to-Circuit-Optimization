#include "ttc/core.hpp"
using namespace ttc;
int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: solver INPUT_PATH OUTPUT_PATH\n";
        return 2;
    }
    try {
        std::ifstream input(argv[1]);
        if (!input) throw std::runtime_error("could not open input");
        Problem p = read_problem(input);
        Netlist result = synthesize(p);
        std::ofstream output(argv[2]);
        if (!output) throw std::runtime_error("could not open output");
        write_netlist(output, p.n, result);
        output.close();
        if (!output) throw std::runtime_error("could not write output");
    } catch (const std::exception& error) {
        std::cerr << "solver: " << error.what() << '\n';
        return 1;
    }
    return 0;
}
