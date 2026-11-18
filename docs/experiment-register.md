# 甲的实验登记

所有结果使用固定方法处理完整真值表，不按 case 名称选择算法。

| 实验 | 内容 | 结论 | 后续 |
|---|---|---|---|
| baseline | 原样交接版及模块化验证 | 25/25 PASS；A/D 与交接记录相同 | 冻结 tag |
| A-20261117-screen | 四种搜索、代数单项、原样基线 | 全部 25/25；局部收益较少，时间增加 | 改批量代数化简、缓存与区域分时 |
| A-20261117-scale | Cut 2/4/6/8/10、束宽/重启/步数递增 | 高强度违反多个原始限时，失败全部保存 | 研究模式测潜力；提交用原始限制 |
| A-20261117-research-deep | 原始函数/成本，仅放宽研究副本时间 | 全部 25/25；不是原始限制下成绩 | 提取廉价收益，减少在线搜索成本 |
| exact/study | SAT 与 MILP，74 次实测 | 25 个局部 SAT 有界最优，MILP20最优5可行未证明 | 通用二输入模板转入在线搜索 |
| exact/templates | 全部16个二输入函数 | 33 个通用候选，非公开答案 | 在线真实门成本和边界时序验收 |

具体配置、版本和各例结果位于同名 results 目录。
完整日志及网表位于 artifacts，随研究归档发布。
最终评测与资源误差分析已完成：

| 实验 | 内容 | 结论 |
|---|---|---|
| A-20261117-final | 基线与默认策略交替五轮 | 全部通过；默认9例面积下降、延迟不变；耗时增加 |
| A-20261117-final-calibrated | 校准后实际交付源码五轮 | 125/125 PASS，全部达标，AD稳定 |
| A-20261117-heldout-fixed | 12/16/20输入新结构、置换、随机电路 | 默认和研究均9/9 PASS；默认另做全行独立验证 |
| A-20261117-cost-model[-calibrated] | 操作成本预测与冷启动校准 | 扫描低估25/28→4/28；公开调参输入证据，非独立泛化 |
| A-20261117-delivery-validation | GitHub干净克隆、单文件导出 | 两版各400通过，导出版官方25/25通过 |

所有正式报告数值来自绑定源码的完整运行；失败与改进版本均保留。

## 尚不属于甲的实现

乙的多方案映射、重代入/跨输出联合优化、变量排序和分组搜索，
仍按协作接口由乙开发；本交付没有将这些计划写成已实现功能。

| 乙的构造实验 | 数据与结论 |
|---|---|
| [同一步优化的 11 种种子](../results/seed-study-linux-20261117/report.md) | 官方五轮共 1,375 次通过，19 例新增 33 个面积／延迟点 |
| [单进程运行保留的 9 种构造](seed-study.md) | 组合在 25 例上五轮全部达标，逐例耗时中位数之和是默认版的 2.56 倍 |

## Stage 1 final integration (2026-11-18)

The nine-seed portfolio is now the course default; explicit TTC_STRATEGY=sweep is the fast control. Final same-machine five-round results: `results/stage1-final-20261118/`. The final group report supersedes the earlier A-only report, preserved under `docs/history/`. Exported standalone validation is recorded separately.
