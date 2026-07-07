# Agent 平台上传说明

本仓库采用两套目录：

1. **源码维护目录**：按业务分类维护，便于人读和协作。
   - `通用能力/<skill-name>/`
   - `效率模块/<skill-name>/`
2. **平台上传目录**：由脚本生成，符合 skill 规范。
   - `dist/agent_upload/.trae/skills/<skill-name>/SKILL.md`

不要直接把源码维护目录整体上传到 Agent 平台。源码目录里有业务分类层级，跨 skill 相对路径不符合平台的扁平 skill 布局。

## 上传前最终验收

上传前先运行：

```bash
python3 tools/verify_project_ready.py
```

该命令会执行 SQL 模板、卡片校验、配置 lint、owner-routing、report publisher、orchestrator 单测、warehouse offline eval、低效策略 smoke、orchestrator shadow CLI、打包、zip 审计、orchestrator live-mode guard 和生产化预检，共 13 个检查项。

验收摘要写入：

```text
dist/final_acceptance/acceptance_summary.json
```

只有确认 `dist/final_acceptance/acceptance_summary.json` 中 `status=passed` 后，才进入 Agent 平台上传。验收临时产物位于 `dist/final_acceptance/tmp/<timestamp>/`，不会发送 Lark、不会写事件主表，也不会覆盖 baseline fixture。

生产化预检可单独运行：

```bash
python3 tools/verify_production_readiness.py
```

Ralph Loop Round 5 实现期间，如 Task 18-21 仍处于未勾选状态，可使用：

```bash
python3 tools/verify_production_readiness.py --allow-open-round5
```

最终验收内部会将 readiness summary 写入 `dist/final_acceptance/tmp/<timestamp>/readiness_summary.json`，并在 `acceptance_summary.json` 中记录该检查项的命令、耗时、产物和失败原因。

## 一键打包

```bash
python3 tools/package_agent_skills.py
```

输出：

```text
dist/agent_upload/
├── .trae/skills/<skill-name>/SKILL.md
├── human_review_monitoring_skills.zip
├── zips/<skill-name>.zip
└── build_summary.json
```

上传方式：

- 如果平台报 `Missing file: SKILL.md`，说明它要求 zip 根目录直接有 `SKILL.md`。这种平台请逐个上传 `dist/agent_upload/zips/<skill-name>.zip`。
- 本平台应上传 `dist/agent_upload/zips/<skill-name>.zip`，该 zip 根目录直接包含 `SKILL.md`。
- 只有平台明确支持批量导入 `.trae/skills` 时，才上传 `dist/agent_upload/human_review_monitoring_skills.zip`。

当前已确认：如果上传 `human_review_monitoring_skills.zip` 报 `Missing file: SKILL.md`，不要再传总包，改传下面 6 个单 Skill 包。

```text
dist/agent_upload/zips/review-monitoring-shared.zip
dist/agent_upload/zips/warehouse-skill.zip
dist/agent_upload/zips/owner-routing.zip
dist/agent_upload/zips/anomaly-touch.zip
dist/agent_upload/zips/low-efficiency-strategy-analysis.zip
dist/agent_upload/zips/monitoring-orchestrator.zip
```

推荐上传顺序：

1. `dist/agent_upload/zips/review-monitoring-shared.zip`
2. `dist/agent_upload/zips/warehouse-skill.zip`
3. `dist/agent_upload/zips/owner-routing.zip`
4. `dist/agent_upload/zips/anomaly-touch.zip`
5. `dist/agent_upload/zips/low-efficiency-strategy-analysis.zip`
6. `dist/agent_upload/zips/monitoring-orchestrator.zip`

## 当前打包范围

打包清单在 `tools/agent_skill_manifest.json`：

- `review-monitoring-shared`
- `warehouse-skill`
- `owner-routing`
- `monitoring-orchestrator`
- `anomaly-touch`
- `low-efficiency-strategy-analysis`

源码侧可以保留测试文件、历史数据产物和历史说明文档，上传包由 manifest 精简生成。当前 `low-efficiency-strategy-analysis` 上传包会排除：

- `assets/**`
- `references/labeling_rate_metric.md`
- `references/data_fetch.md`
- `references/data_readiness.md`
- `scripts/test_sql_templates.py`
- `.DS_Store`、`__pycache__`、`.pytest_cache`、`.pyc`、`.xlsx`、`.tmp` 等缓存、历史产物和临时文件

新增 skill 时：

1. 在源码目录新增 `<skill-name>/SKILL.md`；
2. 确保 frontmatter `name` 与目录名一致；
3. 在 `tools/agent_skill_manifest.json` 的 `skills` 中新增一项；
4. 如有跨目录相对链接，在 `path_rewrites` 中补充上传布局的路径改写；
5. 如需精简上传包，在 manifest 顶层或单个 skill 条目中配置 source-relative `exclude_paths`；
6. 运行 `python3 tools/package_agent_skills.py`。

## 规范要求

每个上传 skill 必须满足：

- 目录名等于 `SKILL.md` frontmatter 的 `name`；
- `SKILL.md` 位于 skill 根目录；
- frontmatter 至少包含 `name` 和 `description`；
- 脚本、参考文档、样例数据必须放在 skill 目录内部；
- 项目内跨 skill 依赖通过 sibling skill 名称和相对路径引用，例如 `../review-monitoring-shared/scripts/card_validator.py`；
- 外部平台能力如 `lark-*`、`sqless`、`bytedcli`、`bytedance-aeolus` 只作为运行时依赖或可选能力引用，不写入项目上传包的 `required_siblings`。

## Zip 审计要求

最终验收会审计 `dist/agent_upload/zips/*.zip`，上传前必须满足：

- 目录下恰好存在 6 个单 Skill zip。
- 每个 zip 根目录直接包含 `SKILL.md`。
- `SKILL.md` frontmatter `name` 与 zip 文件名一致。
- zip 内不包含测试脚本、缓存文件、历史产物、真实 token、真实 open_id、真实 chat_id 或源码分类路径残留。
- Markdown / JSON 中的本地相对路径引用不指向缺失文件。
- JSON 中的 `required_siblings` 不声明外部平台能力。

## 生产副作用边界

`monitoring-orchestrator` 当前 MVP 支持 `manual`、`report_only`、`shadow` 的离线安全链路。`canary` 默认由 live-mode guard 阻断；只有提供匹配的 `production_authorization.v1` 授权文件，且限定到单 SOP、单 report policy、单等级、单目标用户或测试群时，才允许执行受控 canary。`active` / `touch_execute` 仍默认阻断，不支持通过授权文件放行。

真实 Lark / Aeolus 副作用、Agent 平台上传执行、生产事件主表写入和正式触达记录写入仍需平台侧凭证、生产配置校验、目标 allowlist 与人工开关。本地打包和验收命令只证明交付物结构、安全边界和阻断逻辑满足上传前检查，不会自动开启生产执行。

受控 canary 命令形态：

```bash
python3 通用能力/monitoring-orchestrator/scripts/run_orchestrator.py \
  --config <single-target-canary-config.json> \
  --sop-id low_efficiency_labeling \
  --run-mode canary \
  --process-run-dir <process-run-dir> \
  --report-policy-id low_efficiency_p2_detail_report_only \
  --production-authorization-file <production_authorization.v1.json>
```

正式事件触达和状态写回仍需等待真实 owner source、角色目录、目标群 allowlist、事件表/触达记录表写回配置、人工确认门禁和回滚方案齐备后再进入 `active`。

正式事件触达的最小执行入口是：

```bash
python3 通用能力/anomaly-touch/scripts/event_touch_sender.py \
  --hits <level_hits.csv> \
  --route-results <route_results.json> \
  --level P2 \
  --period <period> \
  --output-dir <touch_output_dir> \
  --target-allowlist <approved_target_id>
```

该入口会发送正式触达卡片并写本地 `touch_records.jsonl`，但不会直接写生产事件表或触达记录表；生产表写回仍需显式配置和审批后再开启。

生产写回集成测试入口：

```bash
export HUMAN_REVIEW_BASE_TOKEN=<runtime_private_base_token>
python3 tools/run_low_efficiency_production_integration.py \
  --output-dir dist/production_rollout/original_base_writeback_20260707/integration_flow
```

该脚本会模拟低效策略生产链路的后半段：读取分析结果、路由结果和正式触达记录，按 `idempotency_key` 查询触达记录表；若已存在则更新，若不存在则创建，并把触达记录关联回事件表。每次查询、创建和更新都会写入 `writeback_idempotency.log.jsonl`，用于排查幂等问题。

表化配置导出入口：

```bash
export HUMAN_REVIEW_BASE_TOKEN=<runtime_private_base_token>
python3 通用能力/review-monitoring-shared/scripts/export_base_sop_config.py \
  --sop-id low_efficiency_labeling \
  --raw-output dist/base_config/full_base_table_config_export.json \
  --output dist/base_config/full_base_merged_sop_config.json \
  --lint-output dist/base_config/full_base_validation_report.json \
  --mode shadow \
```

该入口从 Base 读取 SOP-first 配置表，通过后可把合并出的 `sop_config.v1` 作为 `monitoring-orchestrator --config` 输入进行 shadow 验证。

shadow 验证可打开本地写回预览节点：

```bash
python3 通用能力/monitoring-orchestrator/scripts/run_orchestrator.py \
  --config dist/base_config/full_base_merged_sop_config.json \
  --sop-id low_efficiency_labeling \
  --run-mode shadow \
  --process-run-dir <process-run-dir> \
  --baseline-run-dir <baseline-run-dir> \
  --output-dir <shadow-output-dir> \
  --route-preview \
  --state-writeback-preview \
  --dry-run
```

该节点只生成 `state_writeback_preview.json`，不会写事件表或触达记录表。

## 验证命令

最终验收入口是：

```bash
python3 tools/verify_project_ready.py
```

该入口内部会串联以下命令和审计：

```bash
python3 效率模块/low-efficiency-strategy-analysis/scripts/test_sql_templates.py
python3 通用能力/review-monitoring-shared/scripts/test_card_validator.py
python3 通用能力/review-monitoring-shared/scripts/test_config_linter.py
python3 通用能力/owner-routing/scripts/test_route_owner.py
python3 通用能力/anomaly-touch/scripts/test_report_publisher.py
python3 通用能力/monitoring-orchestrator/scripts/test_run_orchestrator.py
python3 通用能力/warehouse-skill/scripts/simulate_offline_eval.py \
  --cases 通用能力/warehouse-skill/examples/warehouse_eval_cases.sample.json \
  --out dist/final_acceptance/tmp/<timestamp>/warehouse_eval_runs.mock.json
python3 通用能力/monitoring-orchestrator/scripts/smoke_low_efficiency_sop.py \
  --output-dir dist/final_acceptance/tmp/<timestamp>/low_efficiency_sop_smoke
python3 通用能力/monitoring-orchestrator/scripts/run_orchestrator.py \
  --config 通用能力/review-monitoring-shared/examples/low_efficiency_sop_config.sample.json \
  --sop-id low_efficiency_labeling \
  --run-mode shadow \
  --process-run-dir 通用能力/monitoring-orchestrator/examples/low_efficiency_run \
  --baseline-run-dir 通用能力/monitoring-orchestrator/examples/low_efficiency_run \
  --output-dir dist/final_acceptance/tmp/<timestamp>/orchestrator_shadow_cli \
  --run-id FINAL-ACCEPTANCE-SHADOW \
  --report-type low_efficiency_grading \
  --route-preview \
  --dry-run
python3 tools/package_agent_skills.py
audit dist/agent_upload/zips/*.zip
python3 通用能力/monitoring-orchestrator/scripts/run_orchestrator.py \
  --config 通用能力/review-monitoring-shared/examples/low_efficiency_sop_config.sample.json \
  --sop-id low_efficiency_labeling \
  --run-mode canary \
  --process-run-dir 通用能力/monitoring-orchestrator/examples/low_efficiency_run \
  --output-dir dist/final_acceptance/tmp/<timestamp>/orchestrator_live_mode_guard \
  --run-id FINAL-ACCEPTANCE-LIVE-GUARD \
  --report-type low_efficiency_grading \
  --dry-run
python3 tools/verify_production_readiness.py \
  --allow-open-round5 \
  --summary-out dist/final_acceptance/tmp/<timestamp>/readiness_summary.json
```
