# AStockLab

AStockLab 是一个在 Windows 本地运行的 A 股“量化研究 + 投资决策辅助”终端。它整合 Qlib/Alpha158/LightGBM、可解释多因子、全市场横截面排名、持仓风险状态机、T+1 回测、实验版本和日报。

它不连接券商、不自动下单，也不输出“保证上涨/必须卖出”。所有结果都应视为研究线索，而不是投资建议。

> 研究优先级：数据正确 > 无未来函数 > 模型稳定 > 风险控制 > 历史收益漂亮。

## 快速启动

双击：

```text
D:\Quant\AStockLab\start_astocklab.bat
```

脚本会激活 `qlib` Conda 环境并启动 Streamlit。也可以在 PowerShell 中运行：

```powershell
cd D:\Quant\AStockLab
C:\Users\10770\miniconda3\envs\qlib\python.exe -m streamlit run app.py
```

进入“数据管理”页面后可点击“更新数据并运行今日分析”。首次完整扫描需要读取全 A Qlib 历史并计算滚动因子；为兼容本机 Windows/沙箱环境，`qlib.kernels` 默认设为 1，首次运行可能需要约 30–45 分钟。后续市场与财务更新优先使用批量接口、DuckDB 和 Parquet 缓存。

## 当前已实现

- 市场总览：涨跌家数、涨跌停近似、成交额、行业强弱、Bull/Neutral/Bear 分类。
- 全市场选股：市场/行业/估值/质量/风险/成交额等过滤，Top 10/20/50/100 和排序。
- 个股分析：价格与均线、各维度分数、综合/Qlib/行业排名、正负贡献解释。
- 我的持仓：手工录入成本和数量，计算收益、排名变化和风险状态。
- 关注列表与风险提醒。
- 可解释多因子：Value、Quality、Growth、Momentum、Trend、Risk、Liquidity。
- Qlib Alpha158 + LightGBM 最新截面推理；原始分仅作排序，不解释为预期收益率。
- Ensemble：默认多因子 50% + Qlib 50%，全部转换为横截面 percentile。
- 回测：T 日收盘信号、T+1 开盘执行，交易费用、滑点、印花税、最小佣金、停牌/涨跌停约束。
- Walk-forward 切分和 Look-ahead/Survivorship/Selection/Overfitting 审计。
- 模型健康：IC、Rank IC、ICIR、20/60 日滚动状态。
- 每日报告、数据质量报告、实验版本留档和可选盘后调度器。
- AKShare 接口的集中适配、重试、超时、字段校验、Parquet 缓存和 stale-cache 降级。
- `src/news/` 与 `src/announcements/` 已预留带发布时间语义的 provider 接口；未来内容只作解释辅助，不直接映射为买卖信号。

## 常用命令

```powershell
# 本地环境、Qlib、DuckDB 健康检查
C:\Users\10770\miniconda3\envs\qlib\python.exe scripts\health_check.py

# 增量更新股票列表、行情快照、最近财报批次
C:\Users\10770\miniconda3\envs\qlib\python.exe scripts\update_data.py

# 完整今日流水线（非关键步骤失败时继续并汇总）
C:\Users\10770\miniconda3\envs\qlib\python.exe scripts\run_today_pipeline.py

# 单独执行因子扫描、Qlib 推理、持仓复评、日报
C:\Users\10770\miniconda3\envs\qlib\python.exe scripts\run_daily_analysis.py
C:\Users\10770\miniconda3\envs\qlib\python.exe scripts\run_qlib_inference.py
C:\Users\10770\miniconda3\envs\qlib\python.exe scripts\run_portfolio_analysis.py
C:\Users\10770\miniconda3\envs\qlib\python.exe scripts\generate_daily_report.py

# 测试
C:\Users\10770\miniconda3\envs\qlib\python.exe -m pytest -q
```

调度器默认关闭。确认 `config.yaml > scheduler.enabled` 后，可以运行 `scripts\run_scheduler.py`；这只做盘后研究更新，不执行交易。

## 架构

```text
Streamlit UI
    ↓
Research/Data services
    ├── AKShareClient → cache → DuckDB/Parquet
    └── QlibDataProvider（只读 D:\Quant\data\qlib_bin）
    ↓
Factors → FactorModel ─┐
                       ├→ Ensemble → Ranking/Explain
Alpha158 → LightGBM ───┘
    ↓
Portfolio state machine / Alerts / Report
    ↓
T+1 Backtest / Walk-forward / Bias Audit / Experiments
```

UI 不直接调用 Qlib 或 AKShare。数据层、因子层、模型层、策略层、回测层和 UI 层保持解耦。

## 数据与时点规则

本地数据库是 `data/astocklab.duckdb`，批量结果保存在 `data/parquet/`。核心表包括：

`stock_master`、`daily_price`、`market_snapshot`、`financial_metrics`、`valuation_metrics`、`industry_info`、`factor_values`、`model_scores`、`daily_rankings`、`portfolio`、`watchlist`、`alerts`、`backtest_results`、`experiments`、`data_quality_reports`。

关键约束：

1. Qlib 原始目录只读，不修改 `D:\Quant\data\qlib_bin`。
2. 内部股票代码统一为 `SH600000`、`SZ000001`、`BJxxxxxx`。
3. 财务数据按 `announcement_date <= signal_date` 做 point-in-time 选择；公告日期缺失时不得声称严格无偏。
4. 所有滚动价格因子只使用当日及此前数据。
5. 回测信号和成交至少错开一个交易日。
6. 当前股票列表批量接口不提供可靠上市日期，因此 120 交易日门槛以可用 Qlib 历史长度执行；后续应补充官方上市日期源。
7. 公共数据接口失败时可以展示缓存，但 UI 必须显示数据时间与告警。

## 模型与评分语义

默认多因子权重为 Quality 25%、Value 20%、Growth 15%、Momentum 20%、Trend 10%、Risk 10%，风险为反向得分。权重是策略参数，不是真理，必须用历史回测验证。

当前 Qlib 文件 `models/qlib_lightgbm.joblib` 是从用户此前成功运行的官方 Alpha158 + LightGBM recorder 导入的 bootstrap 模型。其原实验训练/验证/测试样本较早，适合验证完整推理链路，但不应被当作已经针对 2026 市场重新训练的生产模型。使用 `scripts/train_model.py` 可按 `config.yaml` 的严格时间区间重新训练。

## 回测与防作弊

回测引擎明确实现：

- T 日收盘形成信号，T+1 开盘成交；
- A 股买入后 T+1 才可卖；
- 佣金、最低佣金、印花税和滑点；
- 停牌、主板/创业板/科创板/北交所涨跌停近似限制；
- 动态 Qlib 成分区间用于降低幸存者偏差；
- 财务公告日期审计；
- Walk-forward expanding/rolling 切分；
- Look-ahead、Data Leakage、Survivorship、Selection Bias、Overfitting 提示。

示例回测只验证引擎和研究流程，不代表未来收益。结果保存在 `experiments/<experiment_id>/`，不会因新实验覆盖旧实验。

## 配置与日志

关键参数集中在 `config.yaml`：股票池、上市天数、因子权重、模型时间段、Ensemble 权重、退出确认天数、交易费用、滑点、涨跌停、刷新间隔和调度时间。

日志位于 `logs/`：`app.log`、`data.log`、`model.log`、`error.log`。环境快照位于 `environment_before.txt` 和 `environment_after.txt`；`requirements.txt` 固定本次已验证的直接依赖，Qlib 保持 0.9.7。

## 已知边界

- AKShare 是公共数据源，接口、字段和时效可能变化；AStockLab 会降级而不会把缓存伪装成实时数据。
- 当前实时快照在 Eastmoney 接口不可用时回退到 AKShare 的 Sina 批量接口，部分估值字段可能缺失。
- 历史财务 PIT 质量取决于公告日期覆盖；无法证实的区间会在回测审计中标记风险。
- 当前 LightGBM 是 bootstrap 产物；正式研究前应按当前策略窗口重新训练并做 walk-forward。
- Qlib 与 AKShare 股票覆盖不完全相同；当前排名取两者可用交集并执行历史长度/流动性过滤。
- Windows 传统终端代码页可能让命令行中文股票名显示乱码；数据库、Parquet、Markdown 和 Streamlit 内均保存 Unicode。

## 免责声明

AStockLab 只提供量化研究和风险提示，不构成投资建议。任何真实投资决定都应结合交易所公告、公司原始披露、数据新鲜度和个人风险承受能力独立判断。

