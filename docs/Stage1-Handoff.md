# Stage 1 合并交接 · 2026-11-18

## 最终提交定位

推荐版本：`stage1-final-v1`。组合了甲的局部改写／资源预算／实验工具和乙的多构造种子／共享预算组合。队友分支 `experiment/b-historical-seeds` 已完整保留历史并合入；算法冻结提交为 `84061a2`。随后报告和打包提交不改变 C++ 算法。

正式英文报告在 `docs/stage1-report.md`；可直接提交的 PDF 在 `output/pdf/stage1-report.pdf`。Release 的 `stage1-final.zip` 内有源码、简短编译 README、报告两种格式、交接和评测证据。README 无需任何研究环境变量就能运行。上传 GitHub 不代表已向课程平台提交。

Stage 1 截止：2026-11-19 23:59。团队姓名学号请按课程提交表填写；文档未杜撰成员身份。

## 默认方法到底是什么

一次进程，依次尝试 github、influence-sop、forward-pos、forward-demorgan、forward-top3、reverse-top3、forward-rec3、forward-adaptive3、historical-adaptive 九种构造。构造都从当前真值表计算；没有按 case 名称选方案，也没有复用预存答案。

每种完整构造先规范化，再做一次共同的代数扫描，从扫描前后选择一个实际输出候选；外层保存这些候选的面积／延迟非支配集。先要求 delay 达标，再最小化相对理想面积／延迟的最大损失。并非“最小 delay 后再最小 area”，也不是精确求解 min area s.t. delay <= target。

共享一个 runtime/RAM 预算。首个基础电路作兜底，后续不完整构造／扫描丢弃。最终组合路径没有旧快速版的 100ms 局部搜索窗；它使用 case 剩余预算。正限额预留 max(5ms,10%)，Linux RSS 到限额85%停止可选搜索。首次构造等部分操作不可完整中断，不能声称任意资源限制都保证通过。

原快速版可用 `TTC_STRATEGY=sweep ./build/solver INPUT OUTPUT` 复现。`TTC_STRATEGY=portfolio` 是甲的多种局部搜索组合，不是这次最终的九种子组合，切勿混淆。课程提交运行时不用设置任何变量。

## 复测与结果

`results/stage1-final-20261118/` 是本次同机、原始限制、官方 evaluator 的正式对照。一次预热，交替五轮；final 和 fast 各 125/125 PASS，全部达到目标 delay，A/D 五轮稳定。全部25例和耗时范围在正式报告中，不拼接逐例不同版本最优值。

组合在8例同时不差且至少一项改进，7例相同，10例出现面积／延迟取舍。不是所有case面积都下降。case024由178001/69到149346/63；case007由112652/73到142253/56，属于面积增加换低延迟。

官方分数精确权重未给出；选择组合默认是团队确定的策略，不代表已证明总分更高。runtime 是整个 solver 进程耗时，和电路的抽象 delay 分开。所有公开例没有正RAM上限，另起RSS诊断不代表官方RAM限额测试。

验证：默认400项独立功能／格式／成本检查；局部510候选检查；种子11配置154次完整输出检查。单文件导出也单独编译、验证，记录在 `results/stage1-standalone-20261118/` 和 `results/stage1-standalone-repeat-20261118/`。首轮case011出现TIME_LIMIT，另24例通过；单独诊断33.947ms通过，原失败保留，不以重测覆盖。之后源码／二进制均不改，新增五轮完整25例全部通过（125/125），A/D与模块版一致；正式报告同时记录失败与重测。

## 代码入口与分工

- `src/main.cpp`：默认策略、归档、两路径接口。
- `include/ttc/core.hpp`：原始 BDD、共享门、分组、平衡、极性重映射和选择政策。
- `include/ttc/seed_constructors.hpp`、`historical_order_seed.hpp`：乙的新增顺序／分组／展开构造。
- `include/ttc/seed_pipeline.hpp`：乙的单种子控制和共享预算组合。
- `src/optimization/local_rewrite.cpp`：甲的代数扫描、局部重综合及研究搜索。
- `budget.cpp`、`optimization_api.hpp`：甲的预算／指标／归一化接口。
- `tools/`：完整评测、汇总、报告生成、单文件导出、打包和发布。

没有使用用户另一个未上传的 AIG 项目。没有把计划中的完整 Pareto DP、无限变量 sifting、全局共享重代入或精确整例优化写成已完成。

## 历史研究与继续路线

乙对11种构造做共同后处理的1375次正式测量，新增非支配方案及runtime选择都保存在 `results/seed-study-linux-20261117/`。原组合实测保存在 `results/seed-portfolio-linux-20261117/`；其Mac容器耗时不能与本次WSL混合比较。

甲做过大Cut、贪心、束搜索、退火、多起点、SAT/MILP有界研究及通用模板，失败和超时有记录。它们不是最终默认路径；放宽限制的研究解不当成合法公开case结果。旧甲报告在 `docs/history/`，不是最终提交报告。

Stage2优先：按候选收益/成本动态安排种子，改进共享感知重写，扩展顺序和映射搜索；冻结本tag作全量50例对照。不要拿隐藏集未测当已证明泛化，也不要为追求面积而忽略runtime硬限制。

## 打包、复现与不可变性

按根README编译运行。正式raw CSV、重复轮次、manifest和独立资源诊断保存在results；输入和evaluator只在忽略目录data/local。`VERSION.json`绑定提交包文件，`solver.manifest.json`绑定单文件与模块源码。旧tag/results保持不改。请下载Release提交包后按课程渠道提交源码、README和报告。
