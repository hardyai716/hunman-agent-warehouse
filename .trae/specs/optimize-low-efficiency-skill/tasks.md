# Tasks

- [x] Task 1: 精简低效策略 Skill 文档结构
  - [x] SubTask 1.1: 将 `SKILL.md` 压缩为 process flow，删除重复阈值表和重复口径说明
  - [x] SubTask 1.2: 删除或归档 `labeling_rate_metric.md`、`data_fetch.md`、`data_readiness.md` 的上传依赖
  - [x] SubTask 1.3: 保留并校正 `grading_rules.md`、`analysis_output.md` 的职责边界

- [x] Task 2: 泛化模式 B 为维度拆解
  - [x] SubTask 2.1: 将 `mach_label_breakdown.md` 替换为通用 `dimension_breakdown.md`
  - [x] SubTask 2.2: 将 `analyze_mach_label.py` 泛化为支持 `--dimensions` 的维度拆解脚本
  - [x] SubTask 2.3: 保证 `mach_label` 单维度用例保持兼容

- [x] Task 3: 调整打包产物
  - [x] SubTask 3.1: 更新 `tools/agent_skill_manifest.json`，排除低效策略上传包中的测试、历史口径文档、历史取数文档和 assets
  - [x] SubTask 3.2: 更新 `AGENT_PLATFORM_UPLOAD.md`，说明单 Skill 包与精简上传范围
  - [x] SubTask 3.3: 重新生成 `dist/agent_upload/zips/*.zip`

- [x] Task 4: 验证与回归
  - [x] SubTask 4.1: 运行 SQL 模板单测
  - [x] SubTask 4.2: 运行维度拆解脚本样例测试或冒烟
  - [x] SubTask 4.3: 运行卡片校验单测
  - [x] SubTask 4.4: 校验上传 zip 根目录存在 `SKILL.md`，且不包含排除文件
  - [x] SubTask 4.5: 验证多维拆解打标率分母使用 `review_done` / 完审量
  - [x] SubTask 4.6: 验证上传 zip 无源码分类路径残留

- [x] Task 5: 收口上传元数据依赖边界
  - [x] SubTask 5.1: 将项目内 sibling 与平台内置/外部能力在 Skill metadata 中区分清楚
  - [x] SubTask 5.2: 重新生成上传 zip 并验证 metadata 不会要求未随包上传的 sibling

- [x] Task 6: 修复上传包非运行期残留与失效引用
  - [x] SubTask 6.1: 清理 `warehouse-skill/references/efficiency_domain.md` 中对已排除历史取数文档和测试脚本的引用
  - [x] SubTask 6.2: 更新打包 manifest，使 `review-monitoring-shared.zip` 不包含 `scripts/test_card_validator.py`
  - [x] SubTask 6.3: 重新生成上传 zip，并复核所有 zip 无测试脚本和失效引用

- [x] Task 7: 修复 `review-monitoring-shared` 上传包内失效 Markdown 引用
  - [x] SubTask 7.1: 清理或改写 `dry_run_pitfalls.md` 中指向未打包/不存在文档的引用
  - [x] SubTask 7.2: 清理或改写 `base_schema.md` 中指向未打包/不存在文档的相对链接
  - [x] SubTask 7.3: 重新生成上传 zip，并验证 `review-monitoring-shared.zip` 内 Markdown/SKILL.md 不存在失效相对链接

# Task Dependencies
- Task 2 depends on Task 1 的文档边界决策。
- Task 3 depends on Task 1 和 Task 2 的最终文件结构。
- Task 4 depends on Task 1、Task 2、Task 3。
- Task 5 depends on Task 3 和 Task 4 的上传包复核结论。
- Task 6 depends on Task 4 和 Task 5 的上传包复核结论。
- Task 7 depends on Task 6 的上传包复核结论。
