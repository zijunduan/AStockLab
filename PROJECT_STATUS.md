# AStockLab 项目状态

更新时间：2026-10-08 23:40（Asia/Shanghai）

## 当前阶段

阶段 0–8 的本地 MVP 已完成并通过验收。当前进入“真实日常使用前的模型重训与数据长期积累”阶段。

## 已完成

### 阶段 0：环境与基线

- 复用 `qlib` Conda 环境：Python 3.11.17、Qlib 0.9.7。
- 验证 `D.calendar()` 与 `D.features(["SH600000"], ...)`；6483 个交易日，最新 2026-10-08。
- 保存安装前后环境快照；只安装缺失依赖，未改动 Qlib 数据和源码。
- `pip check`：无依赖冲突。

### 阶段 1：数据层

- AKShare 1.19.1 联网股票列表成功：5572 只。
- 最新市场快照：5571 只；Eastmoney 不可用时已验证 Sina 批量 fallback。
- 2026-06-30 财报批次：5571 只 A 股；ROE 5516 条，营收同比 5569 条。
- DuckDB 核心表、事务 upsert、Parquet 缓存、重试/超时/schema/stale-cache 和数据质量报告均已实现。
- 股票主表刷新会保留已补全的行业/上市日期，不再被轻量接口的空字段覆盖。

### 阶段 2–5：因子、Qlib 与 Ensemble

- Qlib/AKShare 交集历史扫描 5370 只；当前通过 120 交易日门槛并进入排名 4966 只。
- 已实现 Value、Quality、Growth、Momentum、Trend、Risk、Liquidity，含 winsorization、z-score 和 percentile。
- 财务因子按公告日做 PIT 合并；当前排名财务覆盖率 99.78%。
- 已导入用户既有 Alpha158 + LightGBM recorder，完成全市场最新截面推理。
- Ensemble 默认多因子/Qlib 各 50%；最新 Top 20 已写入 DuckDB、Parquet 和日报。
- 重评分已连续运行两次，结果一致，修复了旧财务长表字段与新 PIT 数据重名导致的首轮失效。

### 阶段 3：Streamlit UI

- 市场总览、全市场选股、个股分析、持仓、关注、风险提醒、回测、模型实验室、数据管理和设置页面完成。
- Streamlit headless 启动和 `/_stcore/health` HTTP 200 已通过。
- `start_astocklab.bat` 已生成，可双击启动。

### 阶段 6：持仓与退出

- 手工持仓/关注列表持久化完成。
- 模型恶化、趋势破坏、风险上升、基本面恶化四类独立规则完成。
- HOLD / WATCH / REDUCE_CANDIDATE / EXIT_CANDIDATE 状态机及连续 N 日确认完成。
- 每日流水线自动复评持仓并生成 alerts；当前未录入持仓。

### 阶段 7：回测、Walk-forward 与 Bias Audit

- T 日信号、T+1 开盘执行，买入 T+1 可卖，费用/滑点/印花税/最低佣金/涨跌停/停牌逻辑完成。
- Walk-forward expanding/rolling 生成器完成。
- Look-ahead、财务 PIT、幸存者偏差、选择偏差和过拟合审计完成。
- 已用用户既有 Qlib 样本外预测做一次引擎验收（2017-01-03 至 2020-07-31，Top 20，周调仓）：
  - 累计收益 146.12%，年化 29.77%，Sharpe 1.016，最大回撤 -23.89%；
  - 该结果只证明引擎可运行，不构成未来收益依据；
  - 实验 ID：`4d7de55789ea42138a7888a94581b85d`，配置、净值、交易和偏差审计均已保存。

### 阶段 8：报告、健康与调度

- 日报：`reports/2026-10-08.md`。
- 模型健康：871 个历史截面，历史 Rank IC 0.0487，最近 20 日 Rank IC 0.0407；当前状态 healthy。
- 调度器已实现但默认关闭，避免未经用户确认在后台常驻。
- 模型导入/训练和回测都会写入 experiments，不覆盖旧实验。

## 最终测试

- `python -m compileall -q app.py pages src scripts`：通过。
- `python -m pytest -q`：17 passed（4.73s）。
- `python -m pip check`：No broken requirements found。
- Qlib 健康检查：通过。
- DuckDB schema 检查：通过，无缺表。
- Streamlit 启动健康检查：HTTP 200。
- AKShare 股票列表实网调用：通过；行情 fallback 实际调用：通过。
- 财务重评分幂等验证：连续两次 4966 只，财务覆盖率均为 0.9977849。

## 当前最新数据

- Qlib 日历：截至 2026-10-08。
- 股票主表：5572。
- 市场快照：5571；质量状态 warning（10 条价格暂缺、15 条零成交，按停牌/暂缺处理）。
- 最新排名：4966。
- 当前 Top 5：SH601872、SH600354、SH603259、SH688002、BJ920045。
- 持仓：0；开放风险提醒：0。

## 已知问题与研究边界

1. 当前 Qlib 模型是 bootstrap 产物，其原始样本时间较早；需按 `config.yaml` 重新训练并做 walk-forward，才适合作为当前模型版本。
2. AKShare 公共接口会变化；Eastmoney 快照当前经代理失败，系统已自动使用 Sina 批量接口和缓存，估值覆盖会受影响。
3. 股票列表接口没有可靠上市日期；目前以 Qlib 可用历史长度执行 120 交易日门槛。
4. 历史公告日期并非所有期间都能保证完整；无法证明 PIT 的区间必须在回测中标记，不得宣称严格无偏。
5. 当前示例回测使用 Qlib 复权/归一化价格保持公司行为收益连续性，微观成交限制是研究级近似。
6. 全市场首次因子扫描在单核安全设置下约 30–45 分钟；可在本机验证并行稳定后调整 `qlib.kernels`。

## 下一步建议

1. 用当前配置重新训练 2015–2024 的 Alpha158/LightGBM，并严格保留 2025–2026 样本外区间。
2. 每日盘后积累排名快照，形成真实滚动 IC、候选进出和持仓状态历史。
3. 补充可靠上市日期、历史行业分类与更完整的公告日数据源。
4. 对多因子权重、调仓频率和退出阈值做 walk-forward，而不是针对单次回测优化。
5. 增加更多数据源契约测试，以便 AKShare 升级时及时发现字段变化。

