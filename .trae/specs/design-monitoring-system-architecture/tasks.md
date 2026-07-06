# Tasks

- [x] Task 1: 盘点旧单体 Skill 能力并映射到新架构层
  - [x] SubTask 1.1: 梳理 `/human-review-monitoring` 中感知、判断、路由、触达、状态、配置相关 reference 和脚本
  - [x] SubTask 1.2: 输出旧能力到目标层的映射：warehouse、domain reference、process skill、owner-routing、anomaly-touch、orchestrator、shared
  - [x] SubTask 1.3: 标记哪些旧能力已在当前项目落地，哪些仍缺失

- [x] Task 2: 定义多维表格配置中心的目标模型
  - [x] SubTask 2.1: 基于现有 9 张表定义配置字段的职责边界：运营可配、Agent 回写、系统派生、禁止配置
  - [x] SubTask 2.2: 评估现有 9 张表是否保留、增强、重命名或废弃，并给出迁移理由
  - [x] SubTask 2.3: 定义 SOP-first 配置模型，新增或逻辑定义 SOP 注册表、SOP 节点表、SOP 规则组表、SOP 等级字典表、SOP 角色目录表、业务对象责任映射表、Owner Source 注册表、SOP 运行实例表、Process Skill 注册表、Report Template 注册表
  - [x] SubTask 2.4: 定义可驱动 Agent 串联的最小配置集：`sop_id`、`sop_type`、`metric_id`、`business_domain`、`process_skill`、`domain_reference`、`data_source_id`、`rule_set`、`report_type`、`route_policy`、`touch_policy`、`state_policy`
  - [x] SubTask 2.5: 定义 SOP 等级字典字段：`sop_level_id`、`level_label`、`normalized_severity`、`priority_order`、`sla_minutes`、`requires_human_confirm`、`default_audience_policy`
  - [x] SubTask 2.6: 明确配置变更的校验规则和失败提示格式

- [x] Task 3: 设计 `monitoring-orchestrator` Skill
  - [x] SubTask 3.1: 定义 `monitoring-orchestrator/SKILL.md` 的职责、输入、输出、边界和依赖
  - [x] SubTask 3.2: 定义手动运行、定时运行、报告-only、触达执行四类运行模式
  - [x] SubTask 3.3: 定义 SOP 节点启停和节点顺序如何驱动编排执行
  - [x] SubTask 3.4: 定义 orchestrator 如何按当前 SOP 读取等级字典，不依赖全局 P0/P1/P2 枚举
  - [x] SubTask 3.5: 定义状态机推进规则、停止规则、重试/降级规则和审计日志契约

- [x] Task 4: 设计业务 process skill 注册与调用契约
  - [x] SubTask 4.1: 定义 process skill registry 的配置字段和允许值
  - [x] SubTask 4.2: 定义 process skill 标准输出目录契约：`summary.json`、明细 CSV、汇总 CSV、workbook、provenance
  - [x] SubTask 4.3: 用 `low-efficiency-strategy-analysis` 验证契约可覆盖已跑通的 grading、level detail、dimension breakdown
  - [x] SubTask 4.4: 设计 `review-latency-analysis` 的 process skill 契约，覆盖进审增幅、机审增幅、实时延时、预计全天进审和目标值

- [x] Task 5: 设计配置驱动的报告发布与触达复用方案
  - [x] SubTask 5.1: 将 `anomaly-touch` 中 `publish_lark_report.py` 的 report type、模板名、发送对象、sheet 发布策略纳入配置模型
  - [x] SubTask 5.2: 明确 report publishing 与正式 anomaly touch 的边界：报告推送、事件触达、人工确认、触达记录写入
  - [x] SubTask 5.3: 定义模板注册和 CardKit 模板变量契约
  - [x] SubTask 5.4: 定义 SOP 角色目录如何驱动不同等级的触达对象，如治理 BP、VOC POC、人审运营、CQC 负责人等
  - [x] SubTask 5.5: 定义 `owner-routing` 如何按业务对象粒度解析负责人，例如低效打标 `reason/策略 -> owner`、审核延时 `queue/group/scene -> owner`
  - [x] SubTask 5.6: 定义 Owner Source 注册机制，支持多维表格映射、注册查询逻辑、process skill 输出和人工兜底
  - [x] SubTask 5.7: 定义 `route_result` 标准输出 schema，确保每条结果可追溯到业务 POC、owner_source、route_grain、chat_strategy
  - [x] SubTask 5.8: 定义触达通道策略：默认群聊通知、私聊通知、紧急/持续未处理时临时建群、是否回写 chat_id
  - [x] SubTask 5.9: 定义多条结果对应不同 POC 时的拆分/合并触达规则，避免把结果发给无关 POC

- [x] Task 6: 设计配置可运行性验证机制
  - [x] SubTask 6.1: 定义配置 lint 检查项：必填字段、关联关系、枚举值、Skill 可达性、report type 注册、模板注册
  - [x] SubTask 6.2: 定义 SOP lint 检查项：SOP 是否启用、节点顺序是否合法、规则组是否完整、角色别名是否可解析、owner source 是否注册、route grain 是否在 process skill 输出中存在
  - [x] SubTask 6.3: 定义等级 lint 检查项：规则组引用的 `sop_level_id` 是否存在、优先级/SLA/人工确认/默认受众策略是否完整
  - [x] SubTask 6.4: 定义 dry-run 检查项：数据就绪、SQL 渲染、LIMIT 1 探测、产物生成、卡片渲染
  - [x] SubTask 6.5: 定义 validation report 输出格式，支持运营按表名/字段名修复

- [x] Task 7: 规划迁移路径和验收样例
  - [x] SubTask 7.1: 定义从旧 `human-review-monitoring` 到新多 Skill 的迁移阶段
  - [x] SubTask 7.2: 选择 4 个代表性用例：低效策略 P2、机审标签维度拆解、审核延时 SOP、未来质量域自动处置准确率
  - [x] SubTask 7.3: 为每个用例定义端到端验收：配置读取、取数、判断、报告发布、路由/触达可选、状态记录
  - [x] SubTask 7.4: 对审核延时 SOP 给出 P2/P1/P0 配置样例和规则组表达方式，并说明这些标签只属于该 SOP
  - [x] SubTask 7.5: 对低效打标 SOP 给出 reason/策略 owner 映射样例和 missing owner 处理方式

- [x] Task 8: 设计版本回滚与基线保护方案
  - [x] SubTask 8.1: 定义当前已跑通 baseline，包括低效策略 P2 查询、全等级查询、机审标签维度拆解、飞书表格发布和卡片推送
  - [x] SubTask 8.2: 定义代码回滚策略：Git tag、稳定分支、回滚提交、PR 合并门禁
  - [x] SubTask 8.3: 定义 Skill 上传包回滚策略：保留上一稳定 `dist/agent_upload/zips/*.zip`、manifest 版本、重新上传步骤
  - [x] SubTask 8.4: 定义飞书多维表格配置回滚策略：schema 快照、数据快照、配置版本字段、旧配置只读保护
  - [x] SubTask 8.5: 定义运行入口回滚策略：baseline 命令、新 orchestrator 命令、shadow/canary/active/rollback 模式切换
  - [x] SubTask 8.6: 定义 smoke test 基线：P2 查询、全等级查询、维度拆解、report publishing dry-run、真实私聊卡片发送
  - [x] SubTask 8.7: 定义失败时停止规则：新链路失败不得写事件主表、不得覆盖 baseline 产物、不得触达无关 POC

# Task Dependencies
- Task 2 depends on Task 1 的旧能力盘点。
- Task 3 depends on Task 2 的配置中心目标模型。
- Task 4 depends on Task 2 的配置模型和当前 process skill 输出契约。
- Task 5 depends on Task 2 和 Task 4 的输出契约。
- Task 6 depends on Task 2、Task 3、Task 4、Task 5。
- Task 7 depends on Task 3、Task 4、Task 5、Task 6。
- Task 8 depends on Task 7 的迁移路径和验收样例。

- [x] Task 9: 修复 checklist 未覆盖项：明确上传包 sibling 边界
  - [x] SubTask 9.1: 在设计交付文档中明确外部平台能力（如 `lark-*`、`sqless`、`bytedcli` 等）只能作为运行时/平台依赖或可选能力引用，不要求在项目上传包 manifest 中声明为项目内 sibling。

- [x] Task 10: 复核并固化 P0/P1 实施结果: 确认 SOP-first 配置 lint、report policy、owner-routing MVP、monitoring-orchestrator MVP 与现有架构契约一致，并修复发现的问题。
  - [x] SubTask 10.1: 验证 `review-monitoring-shared` 的 SOP-first 样例配置和 `validation_report.v1` 输出符合设计。
  - [x] SubTask 10.2: 验证 `anomaly-touch` report policy 入口不破坏原 `publish_lark_report.py` CLI。
  - [x] SubTask 10.3: 验证 `owner-routing` 对象级 reason owner 解析和 missing owner 行为符合 `route_result` 契约。
  - [x] SubTask 10.4: 验证 `monitoring-orchestrator` MVP 只执行 report-only/shadow 安全副作用，并能生成审计。

- [x] Task 11: 增强 shadow 对比能力: 为 `monitoring-orchestrator` 增加 baseline run 目录对比能力，输出 shadow comparison summary，用于判断新旧链路差异是否可解释。
  - [x] SubTask 11.1: 支持传入 `--baseline-run-dir` 并读取 baseline 的 `summary.json` 与核心 CSV。
  - [x] SubTask 11.2: 输出 `shadow_comparison.json`，包含行数、Top reason、等级计数和差异摘要。
  - [x] SubTask 11.3: 在 shadow/report-only 模式下只写对比摘要，不写事件主表、不发送触达。

- [x] Task 12: 建立低效策略 SOP-first 固定 smoke fixture: 提供可重复运行的低效策略样例 run 目录和 smoke 命令，支持本地验证 report-only/shadow 链路。
  - [x] SubTask 12.1: 新增最小 `summary.json` 与 CSV fixture，覆盖 P2 命中、已映射 reason、missing owner reason。
  - [x] SubTask 12.2: 新增 smoke 验证脚本或命令入口，串联 config lint、orchestrator report-only、route preview 和 report card dry-run。
  - [x] SubTask 12.3: 确保 fixture 不含真实 open_id、真实 chat_id、真实 token 或敏感数据。

- [x] Task 13: 同步上传包与文档状态: 确认 6 个 Skill 均可打包上传，文档不再遗留“5 个包”或“orchestrator 暂缓”的过期描述。
  - [x] SubTask 13.1: 更新上传说明、README 和架构总览中的模块状态。
  - [x] SubTask 13.2: 验证 `tools/package_agent_skills.py` 产物包含 6 个根级 `SKILL.md` zip 且测试文件被排除。
  - [x] SubTask 13.3: 保持外部平台能力只作为 runtime dependency，不写入项目内 sibling。

# Round 3 Task Dependencies
- Task 10 depends on Task 1-9 的设计交付和当前 P0/P1 实现。
- Task 11 depends on Task 10.4 的 orchestrator MVP 验证。
- Task 12 depends on Task 10 和 Task 11 的安全边界。
- Task 13 depends on Task 10-12 的模块清单与验证结果。

- [x] Task 14: 建立项目最终一键验收入口: 将当前分散的单测、配置 lint、smoke、打包和上传包审计串联为一个可重复执行的最终验收命令。
  - [x] SubTask 14.1: 新增最终验收脚本，顺序执行 SQL 模板、卡片校验、配置 lint、owner-routing、report publisher、orchestrator、warehouse offline eval、低效策略 smoke 和打包命令。
  - [x] SubTask 14.2: 在最终验收脚本中复用临时目录输出运行产物，避免覆盖 baseline fixture 和历史分析结果。
  - [x] SubTask 14.3: 输出机器可读的验收摘要，包含每个检查项的状态、命令、耗时、关键产物路径和失败原因。

- [x] Task 15: 固化上传包最终审计: 对 6 个单 Skill zip 做结构、安全和引用完整性审计，确保可以直接交付 Agent 平台。
  - [x] SubTask 15.1: 校验每个 zip 根目录存在 `SKILL.md`，且 frontmatter `name` 与 zip 名称一致。
  - [x] SubTask 15.2: 校验 zip 中不包含测试脚本、缓存文件、历史产物、真实 token/open_id/chat_id 或源码分类路径残留。
  - [x] SubTask 15.3: 校验 zip 内 Markdown 和 JSON 中的相对路径引用不指向缺失文件，并确认外部平台能力只作为 runtime dependency。

- [x] Task 16: 同步最终交付说明: 将一键验收入口、交付产物位置、离线安全边界和上传步骤写入现有说明文档。
  - [x] SubTask 16.1: 更新 `README.md`，说明最终验收命令、当前 6 个 Skill 模块和安全运行范围。
  - [x] SubTask 16.2: 更新 `AGENT_PLATFORM_UPLOAD.md`，补充最终验收命令、zip 审计结果和平台上传顺序。
  - [x] SubTask 16.3: 确认文档不再遗留过期的 5 包描述、orchestrator 暂缓描述或要求外部平台能力作为项目 sibling 的描述。

- [x] Task 17: 执行最终验收并收口本轮: 运行最终验收入口和必要的补充命令，确认所有任务与检查点均完成。
  - [x] SubTask 17.1: 运行最终验收脚本并确认全部检查通过。
  - [x] SubTask 17.2: 复核 `tasks.md`、`checklist.md` 和最终验收摘要，确保没有未完成项。
  - [x] SubTask 17.3: 追加本轮 `progress.md` 记录，保持 append-only。

# Round 4 Task Dependencies
- Task 15 depends on Task 14.1 的打包产物生成能力。
- Task 16 depends on Task 14 和 Task 15 的最终命令与审计口径。
- Task 17 depends on Task 14-16 的实现和文档同步结果。

- [x] Task 18: 建立生产化预检入口: 新增一个离线安全的生产化 readiness 命令，用于在上传或真实运行前确认本地交付物、验收摘要、上传包和文档状态均满足交接条件。
  - [x] SubTask 18.1: 新增 `tools/verify_production_readiness.py`，读取最终验收摘要、任务清单、检查清单、上传包目录和关键文档，输出机器可读 readiness summary。
  - [x] SubTask 18.2: 预检必须在最终验收失败、任务/检查清单存在未勾选项、6 个 zip 不完整、关键文档缺失或过期描述命中时返回非 0。
  - [x] SubTask 18.3: 预检必须保持离线安全边界，不发送 Lark、不查询 Aeolus、不写事件主表、不覆盖 baseline fixture。

- [x] Task 19: 加固 live 运行模式门禁: 明确 `canary`/`active` 等真实副作用模式在当前 MVP 中只能被生产预检识别和显式阻断，避免误认为已经完成真实触达闭环。
  - [x] SubTask 19.1: 为 orchestrator 增加 live-mode guard 测试或命令探针，确认未显式授权的 `canary`/`active` 运行会失败并给出可行动错误信息。
  - [x] SubTask 19.2: 确认 `report_only`/`shadow` 现有安全链路不受 live-mode guard 影响。
  - [x] SubTask 19.3: 在 readiness summary 中暴露 live-mode 当前状态，明确生产真实副作用仍需平台侧凭证、配置和人工开关。

- [x] Task 20: 将生产化预检纳入最终验收: 扩展最终验收入口，使项目一键验收同时覆盖生产化 readiness 和 live-mode guard。
  - [x] SubTask 20.1: 更新 `tools/verify_project_ready.py`，串联 `verify_production_readiness.py` 或等价检查项，并在 `acceptance_summary.json` 中记录结果。
  - [x] SubTask 20.2: 更新最终验收摘要中的检查项数量和产物路径，确保失败原因可追踪。
  - [x] SubTask 20.3: 保持最终验收临时产物写入独立目录，不覆盖历史分析结果或用户已有文件。

- [x] Task 21: 同步生产化交接说明并完成本轮验收: 更新使用说明并执行完整验证，确保新任务与检查点闭环。
  - [x] SubTask 21.1: 更新 `README.md` 和 `AGENT_PLATFORM_UPLOAD.md`，说明生产化预检命令、live-mode guard、仍需人工完成的真实平台侧动作。
  - [x] SubTask 21.2: 运行最终验收命令和必要的补充探针，确认所有检查通过。
  - [x] SubTask 21.3: 追加本轮 `progress.md` 记录，保持 append-only。

# Round 5 Task Dependencies
- Task 19 depends on Task 18 的 readiness 口径。
- Task 20 depends on Task 18 和 Task 19 的命令或探针结果。
- Task 21 depends on Task 18-20 的实现和验证结果。

- [x] Task 22: 修复 readiness summary 生产人工边界缺口: 在生产化预检摘要中增加机器可读字段，明确真实 Lark/Aeolus 副作用、平台上传和生产事件写入仍需平台侧凭证、配置与人工开关。
  - [x] SubTask 22.1: 更新 `tools/verify_production_readiness.py`，在 readiness summary 中输出结构化 live handoff / manual action 字段。
  - [x] SubTask 22.2: 更新生产化预检自测或最终验收验证，确保该字段稳定存在且语义明确。
  - [x] SubTask 22.3: 重新运行最终验收，确认生产化预检和 live-mode guard 仍通过。

# Round 5 Fix Task Dependencies
- Task 22 depends on Task 18 和 Task 19 的实现结果。
