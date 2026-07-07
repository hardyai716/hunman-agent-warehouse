# SOP-first 表化配置迁移说明

## 结论

SOP 注册和 SOP 节点信息可以迁移到飞书多维表格，且这一步与当前架构一致。推荐先采用“Base 表记录 -> `sop_config.v1` -> `config_linter` -> orchestrator”的编译式迁移，不直接让 orchestrator 在运行时读写配置表。

这样做的收益是：

- 保留现有 JSON 配置作为回滚快照；
- 复用已经通过验收的 `config_linter.py`；
- 避免 Base 权限、字段类型或分页问题影响生产编排；
- 后续可以逐步把运营配置入口从本地 JSON 切到 Base。

## 建议物理表

第一阶段先建配置表，不复用事件表和触达记录表。

| 表名 | 职责 | 主键 |
|---|---|---|
| SOP 注册表 | SOP 根对象、启停、run mode、process skill、默认报告类型 | `sop_id` |
| SOP 节点表 | 编排节点、顺序、启停、失败策略 | `sop_node_id` 或 `sop_id + node_type` |
| SOP 指标观测对象表 | SOP 需要观测的指标或对象 | `metric_id` |
| SOP 规则组表 | SOP 下的等级判定规则和 route grain | `rule_group_id` |
| SOP 等级字典表 | 与 SOP 绑定的等级、SLA、受众策略 | `sop_level_id` |
| SOP 路由策略表 | SOP 如何按业务对象路由 owner | `route_policy_id` |
| Owner Source 注册表 | owner 来源、字段、freshness 与兜底策略 | `owner_source_id` |
| Process Skill 注册表 | process skill 能力、输入输出契约、校验命令 | `process_skill` |
| Report Template 注册表 | report type 与模板、必需产物、变量 | `report_type` |
| 报告发布策略表 | SOP 级报告策略、目标、幂等策略 | `report_policy_id` |

## 当前原 Base 已创建表

以下表已在原 Base 中创建，字段名和可选值优先使用中文，编译层会映射为 `sop_config.v1` 内部字段和值。

| 表名 | table_id | 状态 |
|---|---|---|
| SOP 注册表 | `tbl1XbKnCFRNT9B3` | 已创建，14 个字段 |
| SOP 节点表 | `tblQeV35N4hUQjhk` | 已创建，9 个字段 |
| Process Skill 注册表 | `tbl3Eb1T8UVDjpBy` | 已创建，1 条低效策略 process 记录 |
| Report Template 注册表 | `tblkLMsbCT4qyZVk` | 已创建，3 条低效策略报告模板记录 |
| SOP 指标观测对象表 | `tblolM7J5xosqBkU` | 已创建，1 条低效策略指标记录 |
| SOP 等级字典表 | `tblH70YZBJH3AGvy` | 已创建，4 条低效策略等级记录 |
| SOP 规则组表 | `tblalz3XbnsP8p6X` | 已创建，4 条全等级规则记录 |
| 报告发布策略表 | `tblI8et5gzDGjQol` | 已创建，2 条报告策略记录 |
| SOP 路由策略表 | `tbluiLfUfBAwZ6Xm` | 已创建，1 条 reason 路由策略记录 |
| Owner Source 注册表 | `tbl8gUBe1eXo8y1O` | 已创建，1 条 reason owner source 记录；完全跑通前默认 owner 为当前操作人 |
| 配置治理目录表 | `tbl0JIoqJWVWlIHH` | 已创建，20 条表级治理记录；字段已按运营可读口径命名，不参与配置编译和运行态写回 |

## 运营维护分层

新增 SOP 表不废弃旧表。SOP 表承担“配置控制面”，事件、触达、案例沉淀等旧表继续承担“运行态账本”，数据源、指标、触达模板等旧表继续承担“基础域资产”。

原 Base 已新增 `配置治理目录表`，并创建 5 个运营视图：

| 视图 | 维护层级/筛选 | 当前表数 |
|---|---|---|
| 运营日常维护 | `谁来维护 = 运营日常` | 5 |
| 运营审批维护 | `谁来维护 = 运营审批` | 6 |
| 工程维护只读 | `谁来维护 = 工程维护` | 6 |
| 运行态只读审计 | `谁来维护 = 只读审计` | 2 |
| 兼容旧表待迁移 | `当前定位 = 兼容旧表` | 4 |
| 暂不维护 | `谁来维护 = 暂不维护` | 1 |

运营日常只维护 `SOP 注册表`、`SOP 规则组表`、`SOP 等级字典表`、`Owner Source 注册表` 和 `报告发布策略表`。其他表要么需要审批，要么工程维护，要么只读审计。

完整治理规则见 [config_governance.md](config_governance.md)。

### SOP 注册表字段

| 字段名 | Base 类型 | 说明 |
|---|---|---|
| SOP 标识 | text | 编译为 `sop_id`，例如 `low_efficiency_labeling` |
| SOP 名称 | text | SOP 中文展示名 |
| SOP 类型 | select | 低效打标、审核延时、质量异常、成本异常 |
| 业务域 | select | 效率、质量、成本、延时 |
| 归属团队 | text | SOP 归属团队 |
| 是否启用 | checkbox | SOP 是否启用 |
| 运行频率 | select | 手动、每日、每周、每10分钟、事件触发 |
| 运行模式 | select | 手动、定时、仅报告、影子运行、灰度运行、正式运行、正式触达、回滚 |
| 过程 Skill | text | 编译为 `process_skill`，第一阶段不使用关联字段 |
| 领域知识 | text | 编译为 `domain_reference` |
| 默认报告类型 | text | 编译为 `default_report_type`，第一阶段不使用关联字段 |
| 默认触达策略 | select | 仅报告、预览触达、正式触达 |
| 状态策略 | select | 影子摘要、人工确认、自动推进、停止 |
| 配置版本 | text | 配置版本，用于审计和回滚 |

### SOP 节点表字段

| 字段名 | Base 类型 | 说明 |
|---|---|---|
| SOP 节点标识 | text | 编译为 `sop_node_id` |
| 所属 SOP | text | 编译为 `sop_id`，第一阶段不使用关联字段 |
| 节点类型 | select | 加载配置、配置校验、数据就绪检查、过程分析、责任路由、报告发布、触达发送、审计收尾 |
| 节点顺序 | number | 整数顺序，用于编排执行图 |
| 是否启用 | checkbox | 节点是否启用 |
| 必需输入 | text | JSON 数组或逗号分隔文本 |
| 输出契约 | text | JSON 对象 |
| 失败策略 | select | 阻断、跳过触达、人工确认、重试、仅告警 |
| Dry Run 行为 | text | JSON 对象 |

运行审计表继续保持独立：

- SOP 运行实例表；
- 事件表；
- 触达记录表；
- 案例沉淀表。

## 编译入口

本地表记录样例：

```bash
python3 通用能力/review-monitoring-shared/scripts/table_config_compiler.py \
  --input 通用能力/review-monitoring-shared/examples/low_efficiency_table_config_records.sample.json \
  --output dist/final_acceptance/tmp/compiled_low_efficiency_sop_config.json \
  --lint \
  --mode shadow \
  --sop-id low_efficiency_labeling
```

编译结果是现有 orchestrator 可消费的 `sop_config.v1`。只要 lint 通过，就可以直接替代 `--config`：

```bash
python3 通用能力/monitoring-orchestrator/scripts/run_orchestrator.py \
  --config dist/final_acceptance/tmp/compiled_low_efficiency_sop_config.json \
  --sop-id low_efficiency_labeling \
  --run-mode shadow \
  --process-run-dir <process-run-dir> \
  --dry-run
```

## Base 导出和合并入口

当前已从 Base 读取以下 10 张配置表：Process Skill、Report Template、SOP 注册、SOP 节点、SOP 指标观测对象、SOP 等级字典、SOP 规则组、报告发布策略、SOP 路由策略和 Owner Source。

```bash
export HUMAN_REVIEW_BASE_TOKEN=<runtime_private_base_token>
python3 通用能力/review-monitoring-shared/scripts/export_base_sop_config.py \
  --sop-id low_efficiency_labeling \
  --raw-output dist/base_config/full_base_table_config_export.json \
  --output dist/base_config/full_base_merged_sop_config.json \
  --lint-output dist/base_config/full_base_validation_report.json \
  --mode shadow
```

合并后的配置可直接进入 orchestrator shadow：

```bash
python3 通用能力/monitoring-orchestrator/scripts/run_orchestrator.py \
  --config dist/base_config/full_base_merged_sop_config.json \
  --sop-id low_efficiency_labeling \
  --run-mode shadow \
  --process-run-dir 通用能力/monitoring-orchestrator/examples/low_efficiency_run \
  --baseline-run-dir 通用能力/monitoring-orchestrator/examples/low_efficiency_run \
  --output-dir dist/base_config/full_base_driven_shadow \
  --run-id FULL-BASE-SHADOW-20260707 \
  --route-preview \
  --state-writeback-preview \
  --dry-run
```

2026-07-07 验证结果：

- Base 导出：10 张配置表非空，覆盖 1 条 process、3 条 report template、1 条 SOP、7 条节点、1 条指标、4 条等级、4 条规则、2 条报告策略、1 条路由策略和 1 条 Owner Source；
- `full_base_validation_report.json`：`passed`，0 findings；
- `full_base_driven_shadow/shadow_comparison.json`：`matched`，row count、top reason、level counts 均无差异，warnings 为空；
- `full_base_driven_shadow/run_summary.json`：`completed`。
- 真实低效策略 run 目录验证：`full_base_real_low_efficiency_shadow_with_writeback_preview/` 已完成 shadow，409 条命中全部路由到默认 owner，`missing_owner_count=0`。
- 写回预览：`state_writeback_preview.json` 仅生成本地计划，`write_enabled=false`，不会写事件表或触达记录表。

## 迁移顺序

1. 在测试 Base 建表，只写配置记录，不接 orchestrator。
2. 导出配置记录为本地 JSON，运行 `table_config_compiler.py --lint`。
3. 用编译后的 `sop_config.v1` 跑一次 shadow，对比现有 JSON 配置结果。
4. 通过后把编译产物作为 canary 的只读配置输入。
5. 连续通过后，再把 Base 导出/编译步骤接入发布流程。
6. 最后再评估 orchestrator 是否需要直接接 Base 读取器。

## 强约束

- Base 配置表是配置中心，不能写入运行态探针数据。
- `active` / `touch_execute` 不因表化配置自动放开，仍受 live guard 和授权文件控制。
- 配置变更必须先通过 `config_linter.py`，blocker/error 不得进入取数、触达或写回。
- 真实 Base token 仍只能来自运行环境变量或私有配置，不写入 Git。
