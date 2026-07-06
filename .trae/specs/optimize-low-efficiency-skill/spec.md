# 低效策略 Skill 精简与维度拆解泛化 Spec

## Why
当前 `low-efficiency-strategy-analysis` 已能按 Claude 三层架构跑通，但仍存在旧口径文档、重复取数说明、模式 B 绑定单一维度等冗余。为了后续上传 Agent 平台并降低维护成本，需要把该 Skill 收敛为清晰的 process skill，并把维度拆解能力参数化。

## What Changes
- 精简 `low-efficiency-strategy-analysis` 的上传内容，只保留 process flow、规则说明、输出契约和确定性执行脚本。
- 将模式 B 从“机审一级标签专用模式”泛化为“维度拆解模式”，支持通过参数选择一个或多个允许维度。
- 将 `labeling_rate_metric.md`、`data_readiness.md`、`data_fetch.md` 从上传包中排除或归档，避免与 `warehouse-skill/references/efficiency_domain.md` 重复。
- 更新 `SKILL.md`、维度拆解文档和脚本命名/说明，使模式 A/B 的职责边界更清楚。
- 更新打包脚本和 manifest，保证 Agent 平台上传包精简且根目录包含 `SKILL.md`。
- 执行 SQL 模板测试、维度拆解脚本测试/冒烟、打包校验。

## Impact
- Affected specs: Claude 三层数据分析架构、低效策略分析、Agent 平台上传打包。
- Affected code: `效率模块/low-efficiency-strategy-analysis/SKILL.md`、`references/`、`scripts/`、`tools/agent_skill_manifest.json`、`tools/package_agent_skills.py`、`AGENT_PLATFORM_UPLOAD.md`。

## ADDED Requirements
### Requirement: 通用维度拆解模式
The system SHALL support a dimension breakdown mode that can group low-efficiency reason analysis by configured dimensions instead of hardcoding only `mach_root_label_name`.

#### Scenario: 单维度拆解
- **WHEN** 用户请求按 `mach_root_label_name` 或其他已允许维度拆解低效 reason
- **THEN** 系统按 `day × dimension × reason` 拉取明细并输出维度 × reason 明细与维度汇总

#### Scenario: 多维度拆解
- **WHEN** 用户请求按多个已允许维度组合拆解
- **THEN** 系统按 `day × dimensions × reason` 聚合，并保持打标率分母为完审量

### Requirement: 精简上传包
The system SHALL generate single-skill upload zip files whose root contains `SKILL.md` and excludes non-runtime artifacts.

#### Scenario: 平台校验
- **WHEN** 用户上传 `dist/agent_upload/zips/<skill-name>.zip`
- **THEN** zip 根目录存在 `SKILL.md`
- **AND** 不包含历史 xlsx、pycache、`.DS_Store`、源码分类路径残留

## MODIFIED Requirements
### Requirement: 低效策略 Process Skill
`low-efficiency-strategy-analysis` SHALL only maintain execution flow, grading workflow, dimension breakdown workflow, and references to deterministic scripts. Metrics, field mapping, gotchas, and semantic routing SHALL be delegated to `warehouse-skill/references/efficiency_domain.md`.

### Requirement: 模式 A / 模式 B
模式 A SHALL remain the grading mode for notice/P2/P1/P0. 模式 B SHALL become `dimension_breakdown` and SHALL NOT require adding new modes for each new dimension.

## REMOVED Requirements
### Requirement: 本 Skill 内维护完整指标口径权威
**Reason**: 指标口径和字段映射已迁移到 `efficiency_domain.md`，重复维护会导致漂移。
**Migration**: 删除或排除上传 `labeling_rate_metric.md`，在需要细节时引用 `efficiency_domain.md`。

### Requirement: 上传包包含测试和历史产物
**Reason**: Agent 平台运行不需要单测文件和历史 xlsx 产物。
**Migration**: 源码侧保留测试；上传 manifest 排除测试文件、assets 和历史说明文件。
