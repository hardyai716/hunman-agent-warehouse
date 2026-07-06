* [x] `low-efficiency-strategy-analysis/SKILL.md` 只保留 process flow、模式选择、执行步骤和必要引用

* [x] `low-efficiency-strategy-analysis` 上传包不包含 `labeling_rate_metric.md`、`data_fetch.md`、`data_readiness.md`、`scripts/test_sql_templates.py`、`assets/`

* [x] 维度拆解文档使用通用 `dimension_breakdown` 概念，不再把模式 B 绑定到单一机审一级标签

* [x] 维度拆解脚本支持 `--dimensions`，并能复现原 `mach_label` 单维度输出

* [x] 多维拆解打标率分母为完审量 `review_done`

* [x] `sql_templates.py` 现有 20 个单测全部通过

* [x] `review-monitoring-shared/scripts/test_card_validator.py` 全部通过

* [x] 打包后每个 `dist/agent_upload/zips/<skill>.zip` 根目录包含 `SKILL.md`

* [x] 打包后无 `.DS_Store`、`__pycache__`、`.pyc`、`.xlsx`、历史排除文档残留、源码分类路径残留

* [x] 上传包内 Skill metadata 不把未随 manifest 打包的外部/平台内置能力声明为项目内 sibling

* [x] 上传包内文档不引用已排除的历史取数文档或测试脚本

* [x] 每个 `dist/agent_upload/zips/<skill>.zip` 均不包含测试脚本

* [x] `review-monitoring-shared.zip` 内 Markdown/SKILL.md 不存在指向未打包或不存在文档的失效相对链接
