# UFUG 2106 · Stage 1 跨机器交接文档

**当前完整源码在本文末尾。** 这是当前的 C++17 单线程 Pareto 版，以下称为「Stage 1 基线」。在官方 Linux x86-64 evaluator 的留档测试中，它三轮都通过全部 25 个公开用例，且每例均达到目标延迟。后续改算法请保留这份源码和原始成绩，另建目录实验；Stage 2 要用同一份 Stage 1 方法做对照。

## 1. 先分清：什么算通过，什么影响得分

程序每次读取**一个**用例，运行方式是 `./solver INPUT_PATH OUTPUT_PATH`。输入是真值表、可用门的成本和限制，输出是一张能实现整张真值表的组合电路。程序应能处理新用例，不依赖文件名或预存答案。

| 输入行 | 内容 | 实现时的含义 |
|---|---|---|
| 1–2 | 输入数 `n`、输出数 `m` | 题面写 `1 ≤ n ≤ 18`、`m ≥ 1`；实际这批 25 例为 `n=8…20`、`m=4…16`，不要把 18 写成硬上限。 |
| 3 | `2^n` 个输出串，每串 `m` 位 | 第 `i` 串对应 `i` 的 `n` 位二进制，`x0` 是最高位；串内从左到右是 `y0,…,y(m−1)`。 |
| 4–6 | AND2、OR2、NOT 各自的 `area delay` | 每行两个正整数；「2」指两个输入端，每种门均可用任意次。 |
| 7 | `target_delay` | 电路关键路径的延迟目标，单位与门延迟相同。 |
| 8–9（可选） | 程序运行上限 ms、内存上限 KB | 0 或省略表示该项不限。这批用例均给了时间限制，7 例仅 100 ms；都没给内存上限。 |

输出每行一个门：`ID AND2 a b`、`ID OR2 a b` 或 `ID NOT a`。ID 0 是常数 0，1 到 n 是原始输入；门从 n+1 连续编号，只能引用更小的 ID。末行恰好写 m 个输出信号 ID，不写门数或输出标签。输出可以直接引用输入或 0；常数 1 用 `NOT 0` 产生。

- **PASS**：格式合法、电路无环、全部输入组合的全部输出都正确，且程序满足规定的时间和内存上限。
- **面积 A**：把输出文件中列出的每个门的面积加一次；复用同一门无额外面积，写出无用门仍算面积。
- **电路延迟 D**：输入和常数的到达时间为 0；一个门的输出到达时间为「最晚到达的输入 + 本门延迟」。取所有输出到达时间的最大值。`D > target_delay` 会被扣分，但本身不会使正确电路 FAIL。
- **程序耗时 runtime**：每个用例从 solver 启动到退出的墙钟时间，不含 evaluator 检查电路的时间；与 D 是两回事。

老师邮件确认按同学结果的 **Pareto 排名**比较，面积和延迟都要优化，二者做得好后程序耗时也重要。仅按面积和延迟比较：如果 A 方案两项都不差、且至少一项更好，就「支配」B；若一个面积小、另一个延迟低，二者互不支配。邮件没有给出跨用例汇总公式、runtime 的精确排名方式或分数权重。下文的折中规则是我们从多个候选里交出一个的办法，不能用它推算班级排名或成绩。

## 2. 当前算法：一张真值表怎样变成一个提交电路

所有生产代码都在同一个 `solver.cpp` 里。按下列函数名搜索，比从头读 C++ 更快。

| 去源码找 | 在做什么 | 改这里影响什么 |
|---|---|---|
| `BDD::build` | 按输入变量顺序把函数分为该变量取 0 和 1 时的两张子表。两半相同就跳过该变量；相同子函数在输出之间共享。最后三个变量的八位模式也有缓存。 | 决定之后能复用哪些子电路。当前 `synthesize` 固定用正序，早期版才试正序和逆序。 |
| `BDD::map_top_block`、`Circuit::balance` | 把顶部几层中指向同一个剩余子函数的输入条件合并，再构造 AND/OR 门。可共享条件与门；合并多路信号时，让早到的信号先合并，减少晚到信号经过的门数。 | 最直接改变面积与关键路径。每种尝试都评估原电路和平衡后的电路。 |
| `synthesize`、`remap_area` | 先试顶部宽度 4 的低延迟映射，再按门成本尝试不同宽度、德摩根替换等。重映射从输出向输入推算最晚允许到达时间，在时序余量内尝试节省面积；对快方案也试原延迟和中间预算。 | 用不同构造得到新的面积–延迟组合；内部预算不会修改用例的 `target_delay`。 |
| `Circuit::consider`、`Frontier::accept` | 从输出回溯，按实际可达门算面积、按真实路径算延迟。只给入选方案保存网表，去除无用门并重新编号。 | 保证比较的是最终可输出电路的指标；不要用映射过程中的面积估算替代这里的计算。 |
| `Frontier::take_compromise` | 在留下的候选中选一个，最后由 `write_netlist` 写出。 | 只改这里能改变取舍，但不会创造面积和延迟都更好的新电路。 |

例如，两个输入 `x0,x1` 的单输出列是 `0 1 0 1`。按 `x0` 切开，`x0=0` 时得到 `0 1`，`x0=1` 时也得到 `0 1`；因此结果完全不依赖 `x0`，可直接输出 `x1`，不用门。这就是 BDD 中「两半相同」最简单的一种收益。

**实际选解规则：** 一旦有达标候选，只保留达标候选中不被支配的点；若始终不达标，则先取延迟最小，再比面积、门数。达标点中，记最小面积为 `Amin`、最低延迟为 `Dmin`（可以来自不同电路）。对于每个点，计算相对损失 `a=(A−Amin)/max(1,Amin)` 和 `d=(D−Dmin)/max(1,Dmin)`。先最小化 `max(a,d)`；平手再比较 `a+d`，最后比较面积。这里的「前沿」只包括本程序搜到的点，**不是全体可实现电路的前沿，更不是全班排名**。runtime 在整套 solver 的对照测试中衡量，不参与这个单例的二指标公式。

## 3. 交接基准：已测结果和版本区别

配套 ZIP 的 `reference/` 目录保存官方 CSV 和日志。面积优先版和当前版在同一组用例上各跑三轮，共 150 个「版本 × 轮次 × 用例」记录。`reference/comparison.csv` 包含两版的面积、延迟和耗时。**上版**指面积优先版，不是最初的 BDD 版。

| 三轮官方对照 | 面积优先版 | 当前 Pareto 版 |
|---|---:|---:|
| 每轮 PASS / 达到目标延迟 | 25/25 · 25/25 | 25/25 · 25/25 |
| 25 例面积之和（描述性统计，不是总分） | 723,426 | 728,930 |
| 先取各例三轮耗时中位数，再取 25 例的中位数 | 22.249 ms | 21.121 ms |

16 例的面积和延迟完全不变；其余 9 例（002、010、011、012、013、017、018、022、023）都是**面积上升、延迟下降**。例如 `case_023` 的目标是 24，旧版 `(面积 229, 延迟 24)`，新版 `(272, 20)`。两者都达标，也都不能支配对方。这次改动提供的是取舍，而非 9 次全面胜出。总体面积增加约 0.76%；程序耗时有 12 例变短、13 例变长，不宜用三轮结果宣称稳定提速。

**当前版逐例基准：** 以下每一行三轮均 PASS 且达到目标延迟。面积与延迟取官方网表指标；runtime 为该例三轮中位数。编号 `023` 对应 `case_023.txt`，其他同理。

| 用例 | 目标延迟 | 面积 | 实际延迟 | runtime (ms) |
|---|---:|---:|---:|---:|
| 001 | 77 | 75166 | 55 | 53.718 |
| 002 | 61 | 16746 | 59 | 30.211 |
| 003 | 64 | 25214 | 52 | 27.298 |
| 004 | 57 | 3766 | 37 | 16.097 |
| 005 | 36 | 868 | 26 | 13.943 |
| 006 | 60 | 7752 | 40 | 17.164 |
| 007 | 89 | 112652 | 73 | 168.669 |
| 008 | 62 | 8268 | 34 | 20.310 |
| 009 | 59 | 12665 | 36 | 21.121 |
| 010 | 61 | 10803 | 55 | 55.453 |
| 011 | 40 | 656 | 32 | 16.509 |
| 012 | 40 | 4317 | 34 | 18.820 |
| 013 | 70 | 13268 | 50 | 23.605 |
| 014 | 72 | 19446 | 57 | 88.388 |
| 015 | 81 | 35030 | 62 | 39.881 |
| 016 | 47 | 2730 | 29 | 15.840 |
| 017 | 25 | 615 | 20 | 15.754 |
| 018 | 32 | 3120 | 28 | 17.085 |
| 019 | 73 | 13082 | 57 | 36.746 |
| 020 | 35 | 758 | 26 | 15.438 |
| 021 | 72 | 62590 | 56 | 48.594 |
| 022 | 34 | 1222 | 27 | 15.728 |
| 023 | 24 | 272 | 20 | 14.196 |
| 024 | 83 | 178001 | 69 | 117.894 |
| 025 | 76 | 119923 | 56 | 75.596 |

## 4. 在另一台机器上运行

只带这份 Markdown 就能恢复当前版源码。把本文末尾的 C++ 代码块保存为 `solver.cpp`。如果本机有 macOS、Linux 或 WSL 的 shell，也可以在文件所在目录运行下面的命令自动提取，然后编译。

```sh
awk '/^```cpp$/{copying=1;next} copying && /^```$/{exit} copying' Stage1-Handoff.md > solver.cpp
c++ -O2 -std=c++17 solver.cpp -o solver
```

用题面中的小例子检查命令行接口。三个输入按顺序生成两个输出，满足 `y0 = x0 OR x1` 和 `y1 = y0 AND x2`。

```sh
cat > example.txt <<'CASE'
3
2
00 00 10 11 10 11 10 11
2 2
8 3
1 1
5
CASE
./solver example.txt netlist.txt
cat netlist.txt
```

在本机编译的当前版上，checker 验证了上述 8 行输入全部正确，电路面积为 25、延迟为 7，超出目标 5。这个题面示例独立于第 3 节的 25 个公开用例。手工共享 `y0` 后，一个 OR2 接一个 AND2 即可得到面积 10、延迟 5，可用于检查今后版本的小函数化简效果。

**重跑官方 25 例**时，解压配套的 `Stage1-Test-Kit.zip`，进入解压出的 `stage1/` 目录。当前源码在 `pareto/solver.cpp`，上一版在 `area/solver.cpp`，用例为 `data/stage1/case_001.txt` 至 `case_025.txt`。在有 GCC 的 Linux x86-64 环境中：

```sh
g++ -O2 -std=c++17 pareto/solver.cpp -o solver
chmod +x data/evaluator
./data/evaluator "$PWD/solver" "$PWD/data/stage1" --report "$PWD/result.csv"
```

macOS 或 Windows（WSL）可在已启动的 Docker 中使用 Linux x86-64 环境。以下命令同样从解压后的 `stage1/` 执行，复现两版各三轮的对照。脚本把评测目录复制进容器，恢复官方 evaluator 的执行权限，将输出保存到宿主机的新目录。

```sh
run_dir=$(mktemp -d "$PWD/results.XXXXXX")
docker run --rm --platform linux/amd64 --user "$(id -u):$(id -g)" \
  -v "$PWD/data:/data:ro" -v "$PWD/area:/area:ro" -v "$PWD/pareto:/pareto:ro" \
  -v "$PWD/official.sh:/run-test.sh:ro" -v "$run_dir:/save" \
  gcc:13-bookworm sh /run-test.sh
ls "$run_dir"
```

如需在 macOS 或 Linux 本地逐行校验网表，包内有 `checker.cpp`。编译命令为 `c++ -std=c++17 -O2 checker.cpp -o checker`，运行方式是 `./checker example.txt netlist.txt`。历史本机检查中，`case_023` 得到面积 276、延迟 20，官方 Linux 记录为 272、20。比较改动前后的指标时，使用相同的编译器、平台和编译选项。程序耗时随机器负载变化。

## 5. 接手后的工作

1. 以附录源码和第 3 节成绩为 Stage 1 对照，另存实验版本。修改 `map_top_block` 可产生不同结构的电路。用例 018 的面积从 2471 增至 3120、延迟从 32 降至 28，可用它检验新的分组能否在维持延迟时减少门数。
2. 调整运行时间前，先测量真值表读取、BDD 构造、候选生成和重映射各自的耗时，再用 7 个限时 100 ms 的用例复查。
3. Stage 1 需提交源码和报告，逐例记录通过情况，以及通过用例的面积、电路延迟和程序耗时。Stage 2 需让两个阶段的方法都跑遍两阶段全部公开用例，再报告改动、逐例结果和成员分工。

## 附录 · 当前 Stage 1 完整源码

源码的 SHA-256 为 `a26bba783aaacc1617683a48705e22db59fdb38765d54466ffbf3037533b5bd5`。配套 ZIP 中的 `pareto/solver.cpp` 与此代码块逐字节一致。

```cpp
// UFUG2106 Stage 1: reduced BDD synthesis with several gate mappings.
// Build: c++ -std=c++17 -O2 solver.cpp -o solver
// Run:   ./solver input_path output_path
#include <algorithm>
#include <array>
#include <cstdint>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <queue>
#include <stdexcept>
#include <string>
#include <tuple>
#include <unordered_map>
#include <utility>
#include <vector>

namespace {
using Id = int;
using Score = long long;
enum GateType { AND2, OR2, NOT };
enum Mapping { Direct, ReplaceOr, ReplaceAnd, ProductMux };

struct Problem {
    int n, m;
    std::string table;
    std::array<int, 3> area, delay;
    int target;
};

Problem read_problem(std::istream& in) {
    Problem p{};
    if (!(in >> p.n >> p.m) || p.n < 1 || p.m < 1 ||
        p.n >= std::numeric_limits<std::size_t>::digits) {
        throw std::runtime_error("invalid input or output count");
    }
    const std::size_t rows = std::size_t{1} << p.n;
    if (rows > p.table.max_size() / p.m)
        throw std::runtime_error("truth table too large");
    p.table.reserve(rows * p.m);
    std::string row;
    for (std::size_t i = 0; i < rows; ++i) {
        if (!(in >> row) || row.size() != static_cast<std::size_t>(p.m) ||
            row.find_first_not_of("01") != std::string::npos) {
            throw std::runtime_error("invalid truth table entry " + std::to_string(i));
        }
        p.table += row;
    }
    for (int i = 0; i < 3; ++i) {
        if (!(in >> p.area[i] >> p.delay[i]) || p.area[i] < 1 || p.delay[i] < 1)
            throw std::runtime_error("invalid gate cost");
    }
    if (!(in >> p.target) || p.target < 1)
        throw std::runtime_error("invalid target delay");
    for (int i = 0; i < 2; ++i) {
        in >> std::ws;
        if (in.eof()) return p;
        long long limit;
        if (!(in >> limit) || limit < 0)
            throw std::runtime_error("invalid runtime or RAM limit");
    }
    in >> std::ws;
    if (!in.eof()) throw std::runtime_error("extra input after limits");
    return p;
}

struct Key {
    int type, a, b;
    bool operator==(const Key& other) const {
        return type == other.type && a == other.a && b == other.b;
    }
};

struct Hash {
    std::size_t operator()(const Key& key) const {
        std::uint64_t h = (std::uint64_t(key.type) + 11) * 0x9e3779b185ebca87ULL;
        h ^= (std::uint64_t(key.a) + 1) * 0xc2b2ae3d27d4eb4fULL;
        h ^= (std::uint64_t(key.b) + 1) * 0x165667b19e3779f9ULL;
        return static_cast<std::size_t>(h ^ (h >> 32));
    }
};

struct Gate {
    GateType type;
    Id a, b;
    Score arrival;
};
struct Netlist {
    std::vector<Gate> gates;  // compacted, ordered by the new ID
    std::vector<Id> outputs;
};

struct Candidate {
    Score area, delay;
    Netlist netlist;
};

// Feasible candidates are sorted by increasing area and strictly decreasing delay.
// Before the first feasible solution, keep the fallback with the shortest delay.
class Frontier {
public:
    explicit Frontier(Score target_delay) : target(target_delay) {}

    bool feasible() const { return !points.empty() && points.front().delay <= target; }
    const Candidate& smallest() const { return points.front(); }
    const Candidate& fastest() const { return points.back(); }

    bool may_improve(Score delay) const {
        return delay <= target || points.empty() || delay <= fastest().delay;
    }

    // Allocate storage for a candidate only if its metrics survive the comparison.
    Netlist* accept(Score area, Score delay, std::size_t gate_count) {
        if (!may_improve(delay)) return nullptr;
        if (!points.empty() && !feasible()) {
            const Candidate& fallback = points.front();
            if (std::make_tuple(delay, area, gate_count) >=
                std::make_tuple(fallback.delay, fallback.area, fallback.netlist.gates.size()))
                return nullptr;
            points.clear();
        }
        auto insertion = std::lower_bound(points.begin(), points.end(), area,
            [](const Candidate& c, Score a) { return c.area < a; });
        if (insertion != points.begin() && (insertion - 1)->delay <= delay) return nullptr;
        if (insertion != points.end() && insertion->area == area) {
            if (insertion->delay < delay ||
                (insertion->delay == delay && insertion->netlist.gates.size() <= gate_count))
                return nullptr;
        }
        // All points to the right already have at least this much area.
        auto end = insertion;
        while (end != points.end() && end->delay >= delay) ++end;
        insertion = points.erase(insertion, end);
        return &points.insert(insertion, Candidate{area, delay, {}})->netlist;
    }

    Netlist take_compromise() {
        if (points.size() == 1) return std::move(points.front().netlist);
        const Score ideal_area = smallest().area;
        const Score ideal_delay = fastest().delay;
        // Scale each loss by the best value seen for that metric. We minimize
        // the larger percentage loss. Zero-area or zero-delay optima are direct
        // connections in this positive-cost library and dominate every other point.
        auto penalty = [&](const Candidate& c) {
            long double a = static_cast<long double>(c.area - ideal_area) /
                            std::max<Score>(1, ideal_area);
            long double d = static_cast<long double>(c.delay - ideal_delay) /
                            std::max<Score>(1, ideal_delay);
            return std::make_tuple(std::max(a, d), a + d, c.area);
        };
        auto selected = std::min_element(points.begin(), points.end(),
            [&](const Candidate& a, const Candidate& b) { return penalty(a) < penalty(b); });
        return std::move(selected->netlist);
    }

private:
    Score target;
    std::vector<Candidate> points;
};

class Circuit {
public:
    const Problem& p;
    Mapping mapping;
    Id one = -1;
    std::vector<Gate> gates;

    Circuit(const Problem& problem, Mapping mode)
        : p(problem), mapping(mode), gates(p.n + 1, {NOT, 0, 0, 0}), neg(p.n + 1, -1) {}

    Id invert(Id a) {
        if (neg[a] >= 0) return neg[a];
        Id id = raw(NOT, a, 0);
        neg[a] = id;
        neg[id] = a;
        if (a == 0) one = id;
        return id;
    }
    Id conj(Id a, Id b) {
        if (a == 0 || b == 0 || neg[a] == b) return 0;
        if (a == one || a == b) return b;
        if (b == one) return a;
        if (mapping == ReplaceAnd) {
            Id na = invert(a), nb = invert(b);
            return invert(disj(na, nb));
        }
        return raw(AND2, a, b);
    }
    Id disj(Id a, Id b) {
        if (a == 0 || a == b) return b;
        if (b == 0) return a;
        if (a == one || b == one) return one;
        if (neg[a] == b) return invert(0);
        if (mapping == ReplaceOr) {
            Id na = invert(a), nb = invert(b);
            return invert(conj(na, nb));
        }
        return raw(OR2, a, b);
    }

    // Single pass in reverse topological order marks every gate that reaches an output.
    std::vector<char> reachable(const std::vector<Id>& roots) const {
        std::vector<char> used(gates.size());
        for (Id root : roots) used[root] = 1;
        for (Id i = static_cast<Id>(gates.size()) - 1; i > p.n; --i) {
            if (!used[i]) continue;
            const Gate& gate = gates[i];
            used[gate.a] = 1;
            if (gate.type != NOT) used[gate.b] = 1;
        }
        return used;
    }

    std::vector<Id> balance(Circuit& destination, const std::vector<Id>& roots) const {
        auto used = reachable(roots);
        std::vector<int> refs(gates.size()), memo(gates.size(), -1);
        for (Id id : roots) ++refs[id];
        for (Id i = p.n + 1; i < static_cast<Id>(gates.size()); ++i) {
            if (!used[i]) continue;
            ++refs[gates[i].a];
            if (gates[i].type != NOT) ++refs[gates[i].b];
        }

        std::function<Id(Id)> rewrite;
        // Flatten only private gates so shared subcircuits retain their fanout.
        std::function<void(Id, GateType, std::vector<Id>&)> flatten =
            [&](Id id, GateType type, std::vector<Id>& leaves) {
                if (id > p.n && gates[id].type == type && refs[id] == 1) {
                    flatten(gates[id].a, type, leaves);
                    flatten(gates[id].b, type, leaves);
                } else {
                    leaves.push_back(rewrite(id));
                }
            };
        rewrite = [&](Id id) -> Id {
            if (id <= p.n) return id;
            if (memo[id] >= 0) return memo[id];
            const auto& gate = gates[id];
            if (gate.type == NOT)
                return memo[id] = destination.invert(rewrite(gate.a));
            std::vector<Id> leaves;
            flatten(gate.a, gate.type, leaves);
            flatten(gate.b, gate.type, leaves);
            if (leaves.size() == 2) {
                return memo[id] = gate.type == AND2 ? destination.conj(leaves[0], leaves[1])
                                                    : destination.disj(leaves[0], leaves[1]);
            }
            using Entry = std::pair<Score, Id>;
            std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> queue;
            for (Id x : leaves) queue.emplace(destination.gates[x].arrival, x);
            while (queue.size() > 1) {
                Id a = queue.top().second;
                queue.pop();
                Id b = queue.top().second;
                queue.pop();
                Id merged = gate.type == AND2 ? destination.conj(a, b) : destination.disj(a, b);
                queue.emplace(destination.gates[merged].arrival, merged);
            }
            return memo[id] = queue.top().second;
        };
        std::vector<Id> outputs;
        for (Id id : roots) outputs.push_back(rewrite(id));
        return outputs;
    }

    void consider(const std::vector<Id>& roots, Frontier& frontier) const {
        Score area = 0, delay = 0;
        std::size_t count = 0;
        for (Id id : roots) delay = std::max(delay, gates[id].arrival);
        if (!frontier.may_improve(delay)) return;
        auto used = reachable(roots);
        for (Id i = p.n + 1; i < static_cast<Id>(gates.size()); ++i) {
            if (used[i]) {
                area += p.area[gates[i].type];
                ++count;
            }
        }
        Netlist* accepted = frontier.accept(area, delay, count);
        if (!accepted) return;
        Netlist& best = *accepted;
        best.gates.reserve(count);
        std::vector<Id> new_id(gates.size());
        for (int i = 0; i <= p.n; ++i) new_id[i] = i;
        for (Id old = p.n + 1; old < static_cast<Id>(gates.size()); ++old) {
            if (!used[old]) continue;
            new_id[old] = p.n + 1 + static_cast<Id>(best.gates.size());
            const auto& g = gates[old];
            best.gates.push_back({g.type, new_id[g.a], new_id[g.b], g.arrival});
        }
        for (Id id : roots) best.outputs.push_back(new_id[id]);
    }

private:
    std::vector<Id> neg;
    std::unordered_map<Key, Id, Hash> cache;

    Id raw(GateType type, Id a, Id b) {
        if (type != NOT && b < a) std::swap(a, b);
        Key key{type, a, b};
        auto found = cache.find(key);
        if (found != cache.end()) return found->second;
        Id id = static_cast<Id>(gates.size());
        Score arrival = gates[a].arrival;
        if (type != NOT) arrival = std::max(arrival, gates[b].arrival);
        gates.push_back({type, a, b, arrival + p.delay[type]});
        neg.push_back(-1);
        cache.emplace(key, id);
        return id;
    }
};

struct BNode {
    int var;
    Id lo, hi;
};
class BDD {
public:
    std::vector<BNode> nodes{{-1, 0, 0}, {-1, 1, 1}};
    BDD(const Problem& problem, bool backwards) : p(problem), reverse(backwards) {
        three_input_roots.fill(-1);
    }

    Id build(int output, int level, std::size_t row) {
        if (level == p.n) return p.table[row * p.m + output] - '0';
        if (reverse || p.n - level != 3) return build_node(output, level, row);
        // A three-input subfunction has only eight bits. Reuse its BDD root
        // across every row block and output that contains the same pattern.
        unsigned pattern = 0;
        for (unsigned i = 0; i < 8; ++i)
            pattern |= static_cast<unsigned>(p.table[(row + i) * p.m + output] - '0') << i;
        Id& cached = three_input_roots[pattern];
        if (cached < 0) cached = build_node(output, level, row);
        return cached;
    }
    // Merge the two signals that arrive earliest so late signals travel through fewer gates.
    Id combine(const std::vector<Id>& inputs, Circuit& circuit, bool use_and) const {
        if (inputs.empty()) return use_and ? circuit.invert(0) : 0;
        if (inputs.size() == 1) return inputs.front();
        using Entry = std::pair<Score, Id>;
        std::priority_queue<Entry, std::vector<Entry>, std::greater<Entry>> ready;
        for (Id id : inputs) ready.emplace(circuit.gates[id].arrival, id);
        while (ready.size() > 1) {
            Id a = ready.top().second;
            ready.pop();
            Id b = ready.top().second;
            ready.pop();
            Id merged = use_and ? circuit.conj(a, b) : circuit.disj(a, b);
            ready.emplace(circuit.gates[merged].arrival, merged);
        }
        return ready.top().second;
    }

    Id map_top_block(Id root, Circuit& circuit, std::vector<Id>& memo, int width,
                     std::unordered_map<unsigned, Id>& selector_cache) const {
        if (root < 2) return map(root, circuit, memo);
        width = std::min(width, p.n);
        if (width == 0) return map(root, circuit, memo);

        // For each assignment to the first few variables, collect the selector
        // identifying it under the BDD node that remains. Skipped BDD levels
        // do not need a literal in the selector.
        std::unordered_map<Id, std::vector<Id>> selectors;
        std::vector<Id> literals;
        literals.reserve(width);
        for (int assignment = 0; assignment < (1 << width); ++assignment) {
            Id node = root;
            unsigned signature = 0;
            literals.clear();
            for (int level = 0; level < width && node >= 2; ++level) {
                int variable = reverse ? p.n - 1 - level : level;
                if (nodes[node].var != variable) continue;
                bool high = ((assignment >> level) & 1) != 0;
                Id x = variable + 1;
                // Two bits per level distinguish absent, low and high literals.
                signature |= (high ? 2u : 1u) << (2 * level);
                literals.push_back(high ? x : circuit.invert(x));
                node = high ? nodes[node].hi : nodes[node].lo;
            }
            if (node == 0) continue;
            auto [where, fresh] = selector_cache.try_emplace(signature, 0);
            if (fresh) where->second = combine(literals, circuit, true);
            selectors[node].push_back(where->second);
        }

        std::vector<Id> terms;
        for (auto& entry : selectors) {
            auto& group = entry.second;
            std::sort(group.begin(), group.end());
            group.erase(std::unique(group.begin(), group.end()), group.end());
            Id select = combine(group, circuit, false);
            Id residual = map(entry.first, circuit, memo);
            terms.push_back(circuit.conj(select, residual));
        }
        std::sort(terms.begin(), terms.end());
        terms.erase(std::unique(terms.begin(), terms.end()), terms.end());
        return combine(terms, circuit, false);
    }
    Id map(Id id, Circuit& c, std::vector<Id>& memo) const {
        if (memo[id] >= 0) return memo[id];
        if (id == 0) return memo[id] = 0;
        if (id == 1) return memo[id] = c.invert(0);
        const auto& node = nodes[id];
        Id x = node.var + 1;
        if (node.lo == 0 && node.hi == 1) return memo[id] = x;
        if (node.lo == 1 && node.hi == 0) return memo[id] = c.invert(x);
        if (node.lo == 0) return memo[id] = c.conj(x, map(node.hi, c, memo));
        if (node.hi == 0) {
            Id nx = c.invert(x);
            return memo[id] = c.conj(nx, map(node.lo, c, memo));
        }
        if (node.lo == 1) {
            Id nx = c.invert(x);
            return memo[id] = c.disj(nx, map(node.hi, c, memo));
        }
        if (node.hi == 1) return memo[id] = c.disj(x, map(node.lo, c, memo));
        Id a = map(node.lo, c, memo), b = map(node.hi, c, memo);
        if (c.mapping == ProductMux) {
            Id lo = c.disj(x, a), hi = c.disj(c.invert(x), b);
            return memo[id] = c.conj(lo, hi);
        }
        Id lo = c.conj(c.invert(x), a), hi = c.conj(x, b);
        return memo[id] = c.disj(lo, hi);
    }

private:
    Id build_node(int output, int level, std::size_t row) {
        int var = reverse ? p.n - level - 1 : level;
        Id lo = build(output, level + 1, row);
        Id hi = build(output, level + 1, row | (std::size_t{1} << (p.n - 1 - var)));
        if (lo == hi) return lo;
        Key key{var, lo, hi};
        auto found = unique.find(key);
        if (found != unique.end()) return found->second;
        Id id = static_cast<Id>(nodes.size());
        nodes.push_back({var, lo, hi});
        unique.emplace(key, id);
        return id;
    }

    std::array<Id, 256> three_input_roots;
    const Problem& p;
    bool reverse;
    std::unordered_map<Key, Id, Hash> unique;
};

// Try implementing each wire in either polarity. De Morgan's law lets a gate
// switch type when both inputs and its output are complemented.
void remap_area(const Problem& p, const Netlist& best, Frontier& frontier, Score timing_budget) {
    const Id first = p.n + 1;
    const Id size = first + static_cast<Id>(best.gates.size());
    if (size == first) return;
    const Score infinity = std::numeric_limits<Score>::max() / 4;
    std::vector<Score> required(size, infinity);
    std::vector<int> references(size);
    for (Id output : best.outputs) {
        required[output] = timing_budget;
        ++references[output];
    }
    for (Id i = size - 1; i >= first; --i) {
        const Gate& gate = best.gates[i - first];
        const Score input_time = required[i] - p.delay[gate.type];
        required[gate.a] = std::min(required[gate.a], input_time);
        ++references[gate.a];
        if (gate.type != NOT) {
            required[gate.b] = std::min(required[gate.b], input_time);
            ++references[gate.b];
        }
    }

    // Estimate how much of a shared gate's cost belongs to each consumer.
    // The finished candidate is always ranked again using its exact gate area.
    struct Option {
        double area;
        Score delay;
        bool invert;
    };
    struct Plan {
        std::array<Option, 2> direct, selected;
    };
    std::vector<Plan> plans(size);
    for (Id i = 0; i < first; ++i) {
        plans[i].selected[0] = {0, 0, false};
        plans[i].selected[1] = {static_cast<double>(p.area[NOT]), p.delay[NOT], true};
    }
    for (Id i = first; i < size; ++i) {
        const Gate& gate = best.gates[i - first];
        if (gate.type == NOT) {
            plans[i].selected[0] = plans[gate.a].selected[1];
            plans[i].selected[1] = plans[gate.a].selected[0];
            continue;
        }
        for (int phase = 0; phase < 2; ++phase) {
            const GateType type = phase ? (gate.type == AND2 ? OR2 : AND2) : gate.type;
            const Option& a = plans[gate.a].selected[phase];
            const Option& b = plans[gate.b].selected[phase];
            plans[i].direct[phase] = {
                p.area[type] + a.area / references[gate.a] + b.area / references[gate.b],
                std::max(a.delay, b.delay) + p.delay[type], false
            };
        }
        for (int phase = 0; phase < 2; ++phase) {
            const Option direct = plans[i].direct[phase];
            const Option opposite = plans[i].direct[1 - phase];
            const Option inverted{opposite.area + p.area[NOT],
                                  opposite.delay + p.delay[NOT], true};
            const Score budget = required[i] + (phase ? p.delay[NOT] : 0);
            auto quality = [budget](const Option& option) {
                return std::make_tuple(std::max<Score>(0, option.delay - budget),
                                       option.area, option.delay);
            };
            plans[i].selected[phase] = quality(inverted) < quality(direct) ? inverted : direct;
        }
    }

    Circuit circuit(p, Direct);
    std::vector<std::array<Id, 2>> memo(size, {-1, -1}), direct_ids(size, {-1, -1});
    std::function<Id(Id, int)> emit = [&](Id i, int phase) -> Id {
        Id& result = memo[i][phase];
        if (result >= 0) return result;
        if (i < first) return result = phase ? circuit.invert(i) : i;
        const Gate& gate = best.gates[i - first];
        if (gate.type == NOT) return result = emit(gate.a, 1 - phase);
        bool invert = plans[i].selected[phase].invert;
        int child_phase = invert ? 1 - phase : phase;
        Id& direct = direct_ids[i][child_phase];
        if (direct < 0) {
            Id a = emit(gate.a, child_phase);
            Id b = emit(gate.b, child_phase);
            bool use_and = (gate.type == AND2) != (child_phase != 0);
            direct = use_and ? circuit.conj(a, b) : circuit.disj(a, b);
        }
        return result = invert ? circuit.invert(direct) : direct;
    };
    std::vector<Id> outputs;
    for (Id output : best.outputs) outputs.push_back(emit(output, 0));
    circuit.consider(outputs, frontier);
}

Netlist synthesize(const Problem& p) {
    Frontier frontier(p.target);
    BDD bdd(p, false);
    std::vector<Id> roots;
    for (int j = 0; j < p.m; ++j) roots.push_back(bdd.build(j, 0, 0));

    auto consider_widths = [&](Mapping mapping, const std::vector<int>& widths) {
        Circuit circuit(p, mapping);
        std::vector<Id> memo(bdd.nodes.size(), -1);
        // Every output in this circuit can reuse identical selection conditions.
        std::unordered_map<unsigned, Id> selector_cache;
        for (int width : widths) {
            std::vector<Id> outputs;
            for (Id root : roots) outputs.push_back(bdd.map_top_block(root, circuit, memo, width, selector_cache));
            circuit.consider(outputs, frontier);
            Circuit balanced(p, Direct);
            auto balanced_outputs = circuit.balance(balanced, outputs);
            balanced.consider(balanced_outputs, frontier);
        }
    };

    // The first pass preserves the timing-oriented incumbent.
    bool replace_or_first = p.delay[AND2] + 2LL * p.delay[NOT] < p.delay[OR2];
    Mapping first = replace_or_first ? ReplaceOr : Direct;
    consider_widths(first, {4});
    if (!frontier.feasible()) consider_widths(replace_or_first ? Direct : ReplaceOr, {4});

    // De Morgan replacement is a promising area candidate when its individual
    // gate implementation is cheaper, before any sharing of inverted wires.
    Mapping area_mapping = Direct;
    if (p.area[OR2] > p.area[AND2] + 3LL * p.area[NOT]) area_mapping = ReplaceOr;
    else if (p.area[AND2] > p.area[OR2] + 3LL * p.area[NOT]) area_mapping = ReplaceAnd;
    else if (p.area[AND2] == p.area[OR2]) area_mapping = ProductMux;

    // A width-k selector has up to 2^k terms per output. Limit selector
    // expansion in relation to the size of the current gate graph.
    int wide = std::min(8, p.n);
    while (wide > 2 && (std::size_t{1} << wide) * roots.size() > frontier.smallest().netlist.gates.size())
        --wide;
    std::vector<int> widths{wide};
    // Small circuits can often share more gates with just two selector inputs.
    if (wide > 2 && frontier.smallest().netlist.gates.size() < 1000) widths.push_back(2);
    consider_widths(area_mapping, widths);
    // Keep the fastest seed alive as new entries can replace it in the frontier.
    Candidate fast_seed = frontier.fastest();
    remap_area(p, frontier.smallest().netlist, frontier, p.target);
    if (frontier.feasible() && frontier.smallest().delay > fast_seed.delay) {
        // Try recovering area at the current speed and halfway to the area endpoint.
        const Score midpoint = fast_seed.delay + (frontier.smallest().delay - fast_seed.delay) / 2;
        remap_area(p, fast_seed.netlist, frontier, fast_seed.delay);
        if (midpoint > fast_seed.delay) remap_area(p, fast_seed.netlist, frontier, midpoint);
    }
    return frontier.take_compromise();
}

void write_netlist(std::ostream& out, int n, const Netlist& netlist) {
    const char* names[]{"AND2", "OR2", "NOT"};
    Id id = n + 1;
    for (const auto& g : netlist.gates) {
        out << id++ << ' ' << names[g.type] << ' ' << g.a;
        if (g.type != NOT) out << ' ' << g.b;
        out << '\n';
    }
    for (std::size_t j = 0; j < netlist.outputs.size(); ++j) {
        if (j) out << ' ';
        out << netlist.outputs[j];
    }
    out << '\n';
}
}  // namespace

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
```
