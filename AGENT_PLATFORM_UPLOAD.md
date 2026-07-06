# Agent 平台上传说明

本仓库采用两套目录：

1. **源码维护目录**：按业务分类维护，便于人读和协作。
   - `通用能力/<skill-name>/`
   - `效率模块/<skill-name>/`
2. **平台上传目录**：由脚本生成，符合 skill 规范。
   - `dist/agent_upload/.trae/skills/<skill-name>/SKILL.md`

不要直接把源码维护目录整体上传到 Agent 平台。源码目录里有业务分类层级，跨 skill 相对路径不符合平台的扁平 skill 布局。

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

当前已确认：如果上传 `human_review_monitoring_skills.zip` 报 `Missing file: SKILL.md`，不要再传总包，改传下面 5 个单 Skill 包。

```text
dist/agent_upload/zips/review-monitoring-shared.zip
dist/agent_upload/zips/warehouse-skill.zip
dist/agent_upload/zips/owner-routing.zip
dist/agent_upload/zips/anomaly-touch.zip
dist/agent_upload/zips/low-efficiency-strategy-analysis.zip
```

## 当前打包范围

打包清单在 `tools/agent_skill_manifest.json`：

- `review-monitoring-shared`
- `warehouse-skill`
- `owner-routing`
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
- 跨 skill 依赖通过 sibling skill 名称和相对路径引用，例如 `../review-monitoring-shared/scripts/card_validator.py`。

## 验证命令

打包前建议跑：

```bash
python3 效率模块/low-efficiency-strategy-analysis/scripts/test_sql_templates.py
python3 通用能力/review-monitoring-shared/scripts/test_card_validator.py
python3 通用能力/warehouse-skill/scripts/simulate_offline_eval.py \
  --cases 通用能力/warehouse-skill/examples/warehouse_eval_cases.sample.json \
  --out 通用能力/warehouse-skill/examples/warehouse_eval_runs.mock.json
python3 tools/package_agent_skills.py
```
