# 甲完成交接 · 2026-11-17

## 1. 当前可用成果

仓库：https://github.com/xzx0716/Truth-Table-to-Circuit-Optimization

当前推荐交付tag：`person-a-stage1-v2`（仅修订打包README，算法与v1一致）；初始完整交付tag为`person-a-stage1-v1`。源码变更冻结提交`4413d4d`；随后文档/验证提交不改算法。最终tag对应完整可交接树。GitHub Release包含提交包和研究证据归档。

`stage1-pareto-v1`：队友交接源码原样冻结，SHA256为a26bba783aaacc1617683a48705e22db59fdb38765d54466ffbf3037533b5bd5。
`dev-base-v1`：模块拆分和公共API。
`feature/a-search-runtime`：甲完整开发记录；`main`接收已验证交付。
这些是同一套源码的Git版本，不是多个solver-final文件。

## 2. 编译与提交包

```sh
make
./build/solver INPUT_PATH OUTPUT_PATH
make test
make unit
python3 tools/export_submission.py --output dist/solver.cpp
g++ -O2 -std=c++17 dist/solver.cpp -o dist/solver
```

最终C++单线程、无Python/SAT/MILP依赖。两个路径参数不变。
README、REPORT和源码均在Release提交包。尚未向课程平台发送提交；用户可使用该包按课程渠道提交。

## 3. 模块和分工

- `include/ttc/core.hpp`：交接版BDD、Circuit、原始Frontier、映射与重映射；主干算法基本保留。
- `optimization_api.hpp`：公共网表、成本测量、统一预算和候选回调约定。
- `src/optimization/budget.cpp`：甲的预算、测量、normalize和指标验收。
- `src/optimization/local_rewrite.cpp`：甲的批量代数扫描、Cut、模板、四种研究搜索。
- `src/main.cpp`：预算、完整AD研究归档、选择和输出。
- `research/exact`：真实SAT/MILP、74项规模研究、通用模板生成过程。
- `generated_templates.hpp`：33个通用二输入候选，来源不是公开case答案。
- `tools`：完整评测、分析、导出、打包、发布、成本诊断。

甲任务已实现、试验、文档化并上传。乙的多方案映射、跨输出重代入、变量顺序与递归分组新增模块尚未实现，不能据此报告“整个两人计划完成”。

## 4. 默认与研究版本

默认`sweep`反复批量化简，最多16轮、局部工作窗100ms且服从课程总预算；结构稳定或预算截止即停止。它比每次小替换重建整图便宜。

研究环境：TTC_STRATEGY可选greedy/beam/anneal/multistart/portfolio；TTC_CUT、TTC_ROUNDS、TTC_BEAM、TTC_RESTARTS、TTC_REGIONS、TTC_SEARCH_MS控制力度。
TTC_RESEARCH_MS显式放宽预算，只用于离线研究。不要将其结果写成原限制下成绩。TTC_COST_LOG与TTC_FRONTIER_LOG启用日志，会影响runtime。

实际默认与基线的关系：25例五轮全部通过、达标、AD稳定；9例面积降低，25例延迟不变；面积总和728930→728872，仅下降约0.008%。耗时增加。不要包装成巨大收益。

深度研究case023从272/20→259/20，但约3秒/例；有改善不代表能在100ms内使用。所有失败和高成本版本保留，不默认启用。

## 5. 复现实验

原始用例置于data/local/stage1，evaluator置于data/local/evaluator，chmod +x。Git不带官方测试材料，哈希在docs/input-manifest.json。

```sh
python3 tools/run_experiments.py --solver final=build/solver --out results/NEW-ID --rounds 5 --warmup 1 --save-outputs --rss-probe
python3 tools/analyze_results.py results/NEW-ID/runs.csv
python3 tests/generate_suite.py --out artifacts/NEW-GENERATED
python3 -m pip install -r research/exact/requirements.txt
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python3 tests/test_exact.py
```

既有结果目录不可覆盖。工具会记录源码树/二进制、编译器、输入、环境、轮数和全部失败。性能测量串行执行，不与求解器研究并行。

## 6. 结果目录导航

- baseline：模块化交接版25例初测。
- screen：四种搜索首轮，收益有限后开展加速。
- scale：Cut2..10、束宽/重启递增，原始限时下失败保留。
- research-deep：仅研究副本时间放宽，全25例评估潜力。
- formal：三策略五轮，AD不稳定点不虚构单点。
- final：校准前基线/默认交替五轮，三目标对照。
- final-calibrated：实际交付源码五轮，正式报告主证据。
- correctness-final：六配置各400独立测试。
- heldout：最初文件命名导致evaluator未识别，错误保留。
- heldout-fixed：合法命名后9个新大输入，默认/研究均通过。
- cost-model及calibrated：预测低估、冷启动校准及尾部误差。

详细结果在docs/stage1-report.md，各目录均以A-20261117开头。大日志与网表在Release研究附件。

## 7. 成功后深入与失败备选

成功：批量扫描改善9例且保持delay；继续研究增量指标、共享感知替换、对不同初始种子执行扫描。复杂搜索确有额外改善，应按收益/成本选择区域，而不是只加大固定时间。

失败/昂贵：全图逐个候选复制成本较高；Cut指数增长；模拟退火/束宽增加可能仍停留相似结构。优先缓存、候选索引、廉价筛选和状态多样性，保留基线快速路径。

精确：SAT在小局部完成证明，MILP部分超时。可扩展门数、做对称消除/增量求解，继续生成与公开case无关的通用模板。单位门成本库不代表任意成本下最优。

预测：冷启动校准降低了同输入低估，但非独立泛化；更丰富特征、保守分位数和跨机器验证未完成。首次基础构造、归档、重映射部分不可中断，不能保证极紧限制。

## 8. 给乙的集成说明

在自己的feature/b-mapping-structure分支从main开始。不要替换甲的main或复制solver副本。使用optimization_api.hpp的RuntimeBudget、Netlist独立快照和CandidateSink。
新增映射/共享/分解入口按docs/collaboration.md；所有模块共用一次总截止，不能各自重新计满runtime_limit。中止只能放弃未完成候选，不破坏已有Archive。

整合后再做B单项、A单项、B→A、A→B和交替迭代消融。已有Stage1 tag不移动，Stage2时恢复冻结源码并与新方法一起跑50例。当前没有Stage2或隐藏测试结果。

## 9. 最优性和成绩边界

完整case交付的是最佳已知非支配结果。只有SAT/MILP完成限定范围证明的小问题标为有界最优；MILP状态为数值求解器证明状态，未导出形式化证书。官方跨case权重和runtime排名公式未知。内部选择规则、面积和、Pareto点数都不是官方总分。
