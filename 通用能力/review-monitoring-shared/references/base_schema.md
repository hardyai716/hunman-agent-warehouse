# 飞书多维表格字段结构

**Base Token:** `<BASE_TOKEN>`（真实值应放在私有配置或运行环境中）
**获取时间:** 2026-07-01
**获取方式:** `lark-cli base +field-list --as user`

---

## 1. 数据源表 (tblykQRCZjiqdhX5) — 共14个字段

| 序号 | 字段ID | 字段名 | 类型 | 选项/说明 | 描述 |
|------|--------|--------|------|-----------|------|
| 1 | fldbiZDo9T | 数据源名称 | text(文本) | plain | — |
| 2 | fldj2Y2ano | 数据源类型 | select(单选) | 风神数据集、RDS表、API、多维表格 | 决定取数底座路由 |
| 3 | fldVecnrG1 | 数据源ID | text(文本) | plain | 数据源唯一标识 |
| 4 | fldgDWi2Zu | 数据集/表标识 | text(文本) | plain | 风神数据集ID / RDS表名等，具体值由运营在数据源表按数据源类型填写 |
| 5 | fldqnGKmwZ | 数据地址 | text(文本) | plain | 看板/图表链接或数据集详情页 URL |
| 6 | fldgME3vHU | 查询口径 | text(文本) | plain | 取数 SQL/语义描述，字段名以指标注册表为准 |
| 7 | fldBvwEmpH | 日期字段 | text(文本) | plain | 如 p_date |
| 8 | fldoTNFZ7m | 维度字段 | text(文本) | plain | 如 reason,scene |
| 9 | fldpcKKoB7 | 指标字段 | text(文本) | plain | 指标计算涉及字段，如 完审量_reviewid、打标量_reviewid、打标率__reviewid |
| 10 | fldGUbfvHx | 数据延迟天数 | number(数字) | — | 权威字段，T+N 对应 N。Skill 按此字段计算目标分区。 |
| 11 | fldzvkqAPy | 更新频率 | select(单选) | 日更、周更 | — |
| 12 | fldYFlY3Rs | 数据就绪状态 | select(单选) | 未校验(Gray)、已就绪(Green)、未到位(Orange)、异常(Red) | Skill 执行前的数据可用性校验结果。未到位/异常时应跳过撞线判断，避免误报。 |
| 13 | fldWSEgRV7 | 最近就绪校验时间 | datetime(日期时间) | 格式: yyyy/MM/dd HH:mm | Skill 写入，每次就绪校验后更新 |
| 14 | fldehhWk18 | 创建时间 | created_at(创建时间) | 格式: yyyy/MM/dd | — |

---

## 2. 指标注册表 (tblKsDBLYwSHSNwm) — 共14个字段

| 序号 | 字段ID | 字段名 | 类型 | 选项/说明 | 描述 |
|------|--------|--------|------|-----------|------|
| 1 | fldtWimAWC | 指标ID | text(文本) | plain | 唯一标识，如 metric_low_label_rate_strategy |
| 2 | fld2OW520U | 指标名称 | text(文本) | plain | 如 近7天高完审低打标策略 |
| 3 | fld8gyvvpk | 模块 | select(单选) | — | 指标所属业务模块 |
| 4 | fldnEotVtj | 是否启用监控 | checkbox(复选框) | — | — |
| 5 | fldY8fyjAK | 监控频率 | select(单选) | 日度、周度 | 决定调度节奏 |
| 6 | fldWIKbIWt | 统计粒度 | text(文本) | plain | 如 reason+scene |
| 7 | fldqayKVzK | 指标口径 | text(文本) | plain | 计算方式描述，如 打标率=打标量/完审量 |
| 8 | fld9FJQP84 | 基础过滤条件 | text(文本) | plain | 权威字段，样本池/基础过滤条件。Agent 直接拼进 SQL，无需 Python 解析。 |
| 9 | fldJWgXjpP | 目标阈值 | number(数字) | — | 权威字段，如 0.01 |
| 10 | fldDW016fW | 目标方向 | select(单选) | ≤、≥、<、> | 权威字段，与「目标阈值」配合使用 |
| 11 | fldElPG83h | 目标单位 | select(单选) | 比率、绝对值、百分比 | 权威字段 |
| 12 | fldLHorsug | 数据源 | link(关联) | 关联数据源表 | — |
| 13 | flduAGgvIT | 指标负责人 | user(人员) | — | — |
| 14 | fldIeHBWRr | 创建时间 | created_at(创建时间) | — | — |

---

## 3. 撞线规则表 (tbl73HpcA7rWtJ8T) — 共11个字段

当前状态：legacy 兼容表。SOP-first 低效策略以 `SOP 规则组表` 为规则权威源，当前 Agent 不读取本表作为新 SOP 配置入口。

| 序号 | 字段ID | 字段名 | 类型 | 选项/说明 | 描述 |
|------|--------|--------|------|-----------|------|
| 1 | fldTbcnTQF | 规则ID | text(文本) | plain | 唯一标识，如 rule_low_label_rate_p1 |
| 2 | fldcvgyaXm | 来源案例 | link(关联) | 关联案例沉淀表 | 该规则来源于哪个历史案例，便于追溯 |
| 3 | fldB0EYtoE | 关联指标 | link(关联) | 关联指标注册表 | — |
| 4 | fldM25Fb8N | 规则状态 | select(单选) | 生效、停用、草稿 | — |
| 5 | fldeK5hd70 | 等级(字典) | link(关联) | 关联等级字典表 | — |
| 6 | fldJC5jrre | 规则描述 | text(文本) | plain | 运营按标准模板填写完整查询口径（【数据口径】/【前置过滤】/【触发条件】/【输出字段】/【补充说明】五章节）。Skill 按模板解析后直接拼 SQL 交风神执行，**查询结果非空即代表撞线**。**不含样本池约束**（样本池约束统一在指标注册表「基础过滤条件」维护）。 |
| 7 | fldKceOTnn | 最小样本量 | number(数字) | — | 低于此值降低置信度，不生成高等级事件 |
| 8 | fldjd8Wgbc | 命中事件 | link(关联) | 关联事件表 | — |
| 9 | fldm3RoIhg | 创建时间 | created_at(创建时间) | — | — |
| 10 | fldZJPogOO | sql_key | select(单选) | rule_low_label_rate_notice、rule_low_label_rate_p1、rule_low_label_rate_p2、rule_low_label_rate_p0 | 撞线判断 SQL 模板键，**按规则 ID 命名**（key 与规则 ID 一一对应，非按 SQL 骨架命名）。非空走模板路径，为空回退规则描述自然语言兜底路径。值域必须与 scripts/sql_templates.py 的 SQL_TEMPLATES key 严格一致；新增规则模板后需同步补充本单选项。 |
| 11 | fldpVXh0sW | sql_params | text(文本) | plain | 该模板 required_params 的扁平 JSON 取值（阈值/算子/字段名/排序字段）。由 rule_intake/Agent 代填代验，运营不手写。 |

---

## 4. 等级字典表 (tblgcg6zvhaY3Qrw) — 共5个字段

当前状态：legacy 兼容表。SOP-first 低效策略以 `SOP 等级字典表` 为等级/SLA/人工确认权威源，当前 Agent 不读取本表作为新 SOP 配置入口。

| 序号 | 字段ID | 字段名 | 类型 | 选项/说明 | 描述 |
|------|--------|--------|------|-----------|------|
| 1 | fldLqbfj9i | 等级 | text(文本) | P0、P1、P2、notice | — |
| 2 | fldRLpQMMo | 优先级排序 | number(数字) | — | 数字越小优先级越高，多规则命中时取最高等级 |
| 3 | fldKoBWRvP | 默认响应时长 | text(文本) | plain | 渲染文案，如"2小时内响应"。触达消息中的 `{sla}` 变量取此字段。 |
| 4 | fldKw6WtAk | 默认响应分钟 | number(数字) | — | SLA 计算权威，如 120。SLA截止时间 = 事件创建时间 + 此字段（分钟）。 |
| 5 | fldFzR90Aa | 是否需要人工确认 | checkbox(复选框) | — | legacy 字段。SOP-first 低效策略以 `SOP 等级字典表` 为权威源；本字段仅供旧链路兼容参考。 |

---

## 5. 责任路由表 (tblvFGVbTBQ3Vfws) — 共12个字段

当前状态：legacy 兼容表。SOP-first 低效策略以 `Owner Source 注册表` 和 `SOP 路由策略表` 为路由权威源，当前 Agent 不读取本表作为新 SOP 路由入口。

| 序号 | 字段ID | 字段名 | 类型 | 选项/说明 | 描述 |
|------|--------|--------|------|-----------|------|
| 1 | fldlbRP6zm | 路由ID | text(文本) | plain | — |
| 2 | fldUfJF9Ya | 关联指标 | link(关联) | 关联指标注册表 | — |
| 3 | fld83x2Gee | 等级(字典) | link(关联) | 关联等级字典表 | — |
| 4 | fldcDsEaL1 | 适用范围 | text(文本) | plain | 精确匹配场景值 |
| 5 | fld1vYEkeI | 主负责人 | user(人员) | — | — |
| 6 | fldxeUadIr | 协作方 | user(人员) | — | — |
| 7 | fldRg4kGls | 升级人 | user(人员) | — | — |
| 8 | fldi7chdJ4 | 触达渠道 | select(多选) | 飞书群、私聊 | — |
| 9 | fldJ4jDodR | 群聊/接收方 | text(文本) | plain | 群名，如"抖音安全-人审监控"。为空时由 touch_sender 建群后自动回写新群名。 |
| 10 | fldzVXrZB8 | 群聊ID | text(文本) | plain | 飞书 chat_id（oc_xxx）。首次建群后由 touch_sender 自动回写，后续复用，无需人工填写。 |
| 11 | fldOFdgzkc | 是否启用 | checkbox(复选框) | — | 路由是否生效 |
| 12 | fldASmNGZy | 创建时间 | created_at(创建时间) | — | — |

---

## 6. 触达模板表 (tblDLzboh47WqJla) — 共9个字段

当前状态：legacy/预留表。低效策略报告结构来自 Skill 内模板和 Report Template 注册表，当前 Agent 不读取本表。

| 序号 | 字段ID | 字段名 | 类型 | 选项/说明 | 描述 |
|------|--------|--------|------|-----------|------|
| 1 | fldaQVZaA8 | 模板ID | text(文本) | plain | — |
| 2 | fldCbNhzqZ | 模板场景 | select(单选) | 首次触达、升级通知、复查通知 | — |
| 3 | fldVizJYqX | 等级(字典) | link(关联) | 关联等级字典表 | — |
| 4 | fldtaP7ZRm | 接收对象 | select(单选) | 业务负责人、一线执行人、管理者 | — |
| 5 | fld58lFC6q | 标题模板 | text(文本) | plain | 含 `{level}`、`{metric}` 等变量 |
| 6 | fldROYUcTw | 正文模板 | text(文本) | plain | 含全部变量占位符 |
| 7 | fldZuexyot | 必填变量 | text(文本) | plain | 逗号分隔的变量名列表，缺少时报 missing_variables |
| 8 | fld1XeVIZa | 是否启用 | checkbox(复选框) | — | 模板是否生效 |
| 9 | fldy7uT7VT | 创建时间 | created_at(创建时间) | — | — |

---

## 7. 事件表 (tblHOC5Y8j58xDYQ) — 共25个字段

| 序号 | 字段ID | 字段名 | 类型 | 选项/说明 | 描述 |
|------|--------|--------|------|-----------|------|
| 1 | fldYQHgLds | 事件ID | auto_number(自动编号) | — | 唯一标识，如 EVT-20260626-0001 |
| 2 | fld7ea5QOU | 事件标题 | text(文本) | plain | — |
| 3 | fldN9qsjdv | 关联指标 | link(关联) | 关联指标注册表 | — |
| 4 | fldeKmcLgr | 当前状态 | select(单选) | 待判断、待触达、处理中、待验证、待关闭、已解决、已升级、误报 | 状态机唯一权威，只由 flow_orchestration 推进 |
| 5 | fldGmTn8Fv | 等级(字典) | link(关联) | 关联等级字典表 | 由 anomaly_judgement 回写 |
| 6 | fldx18556s | 业务对象 | text(文本) | plain | 如 reason_1001 |
| 7 | fld3DJWL7v | 场景/范围 | text(文本) | plain | 如 抖音安全审核 |
| 8 | fldgKBwSTJ | 当前值 | number(数字) | — | — |
| 9 | fldohCudBE | 目标/基线值 | number(数字) | — | 事件创建时从指标注册表冗余写入，便于归因时对比，不随指标注册表变化。 |
| 10 | fldHrHg22x | 影响说明 | text(文本) | plain | 由 anomaly_judgement 回写，描述影响面与置信度 |
| 11 | flduFeFzuI | 疑似原因 | text(文本) | plain | 由 root_cause_analysis 回写 |
| 12 | fldAp7wZJn | 建议动作 | text(文本) | plain | 由 root_cause_analysis 回写 |
| 13 | fldssalruo | 后续动作 | text(文本) | plain | 由 resolution_action 回写，记录实际执行内容与操作回执 |
| 14 | fldUJ6azlw | 关闭原因 | select(单选) | — | 由 resolution_tracking 回写 |
| 15 | fldEOW2afX | 复盘摘要 | text(文本) | plain | 由 resolution_tracking 回写 |
| 16 | fldU85qYBa | 责任方 | user(人员) | — | 由 owner_routing 回写 |
| 17 | fldzl1gtjg | 协作方 | user(人员) | — | 由 owner_routing 回写 |
| 18 | fldlEATNPZ | SLA截止时间 | datetime(日期时间) | — | 由 owner_routing 回写；= 事件创建时间 + 等级字典表「默认响应分钟」 |
| 19 | fldqjP22qM | 触达记录 | link(关联) | 关联触达记录表 | 由 touch_sender 回写 |
| 20 | fld5AojaGZ | 最近触达时间 | datetime(日期时间) | — | 由 touch_sender 回写 |
| 21 | fldldltfKY | 路由触达摘要 | text(文本) | plain | 由 touch_sender 回写，格式：{等级} {周期} 发现 {X} 条 {规则名} |
| 22 | fldmrPhWqP | 命中规则关联 | link(关联) | 关联撞线规则表 | 记录该事件命中的撞线规则 |
| 23 | fldraxSHGH | 预计治理完成时间 | datetime(日期时间) | — | 治理排期，处理中回写 |
| 24 | fld5dyh4oC | 最近复查时间 | datetime(日期时间) | — | 由 resolution_tracking 回写 |
| 25 | fldp6HQGYs | 创建时间 | created_at(创建时间) | — | 事件创建时间 |

---

## 8. 触达记录表 (tbl39ZotgZJ8Q8aL) — 共16个字段

| 序号 | 字段ID | 字段名 | 类型 | 选项/说明 | 描述 |
|------|--------|--------|------|-----------|------|
| 1 | fld4mt0vxJ | 触达ID | auto_number(自动编号) | — | 唯一标识，如 TR-20260626-0001 |
| 2 | fldpbuISoh | 触达标题 | text(文本) | plain | — |
| 3 | fldmeAsNPz | 触达内容 | text(文本) | plain | — |
| 4 | fldWBaxAkY | 触达对象 | user(人员) | — | — |
| 5 | fldOMBNYDD | 触达渠道 | select(单选) | 飞书群、私聊 | — |
| 6 | fldM6ISiwg | 群聊ID | text(文本) | plain | — |
| 7 | fldZovgO4N | 消息ID | text(文本) | plain | 飞书 message_id（om_xxx）。同等级批量触达时多条记录共享同一 message_id。 |
| 8 | fld7QgsnHS | 触达状态 | select(单选) | 已发送、待人工确认、失败 | — |
| 9 | fldPVA4Zaf | 触达时间 | datetime(日期时间) | — | — |
| 10 | fldz0pHZVF | 关联事件 | link(关联) | 关联事件表 | — |
| 11 | fldfBiBeXs | 关联责任路由 | link(关联) | 关联责任路由表 | — |
| 12 | fldoxOgEGU | 关联触达模板 | link(关联) | 关联触达模板表 | legacy 关联字段，当前低效策略写回不使用 |
| 13 | fldUc3FVF5 | 是否需要人工确认 | checkbox(复选框) | — | 运行时快照字段，不是权威配置来源；SOP-first 链路以 SOP 等级配置为准。 |
| 14 | fldfAfQiFq | confirmed_by | user(人员) | — | 人工确认人，P0/P1 确认后回写 |
| 15 | fldl1tKJeb | confirmed_at | datetime(日期时间) | — | 人工确认时间，P0/P1 确认后回写 |
| 16 | fldntXE7RR | confirm_message_id | text(文本) | plain | 人工确认消息 ID，P0/P1 确认后回写 |

---

## 9. 案例沉淀表 (tblXrNg8vSXlhSFB) — 共12个字段

当前状态：MVP 暂未启用。未来可由 case_to_rule 或关闭/复盘流程写入，用于存储已关闭事件的处理经验；当前 Agent 不读取、不写入。

| 序号 | 字段ID | 字段名 | 类型 | 选项/说明 | 描述 |
|------|--------|--------|------|-----------|------|
| 1 | fldMtZx1ZK | 案例ID | auto_number(自动编号) | — | 唯一标识 |
| 2 | fldbIAyUXE | 案例标题 | text(文本) | plain | — |
| 3 | fldsVaPrWF | 最终原因 | text(文本) | plain | 根因结论 |
| 4 | fldslrVXzV | 有效动作 | text(文本) | plain | — |
| 5 | fldJrt44yi | 无效动作 | text(文本) | plain | — |
| 6 | flddHfgB8j | 适用范围 | text(文本) | plain | — |
| 7 | fldbJZwayb | 是否已转规则 | checkbox(复选框) | — | — |
| 8 | fldFF5CwMv | 是否需更新Skill | checkbox(复选框) | — | — |
| 9 | fldXVKCuYx | 关联指标 | link(关联) | 关联指标注册表 | — |
| 10 | fldBhTzf5s | 关联事件 | link(关联) | 关联事件表 | — |
| 11 | fld8FeAoAl | 关联撞线规则 | link(关联) | 关联撞线规则表 | — |
| 12 | fld2hVzZy1 | 创建时间 | created_at(创建时间) | — | — |

---

## 10. 配置治理目录表 (tbl0JIoqJWVWlIHH) — 共11个字段

补充时间：2026-07-07。该表只用于表级治理和运营可见性，不参与 `sop_config.v1` 编译，也不参与运行态写回。

| 序号 | 字段ID | 字段名 | 类型 | 选项/说明 | 描述 |
|------|--------|--------|------|-----------|------|
| 1 | fldTuFESFk | 配置表名称 | text(文本) | plain | 这张表在 Base 里的中文名称。运营同学先看这个字段判断是哪张表。 |
| 2 | fldBQXj8sW | 系统表ID（无需填写） | text(文本) | plain | 系统识别用的 Base table_id。运营同学一般不用理解或填写；排障、脚本和工程联动时使用。 |
| 3 | fldX756Hpa | 表类型标签 | select(多选) | 权威配置、基础域资产、运行产物、兼容旧表、工程契约、运营日常维护、运营审批维护、只读审计 | 说明这张表属于哪类用途，一个表可以有多个标签。 |
| 4 | fld6NZL8A3 | 当前定位 | select(单选) | 权威源、基础域权威、运行产物、兼容旧表、样例测试 | 说明这张表在当前系统中的定位。 |
| 5 | fld3ahKOo3 | 谁来维护 | select(单选) | 运营日常、运营审批、工程维护、只读审计、暂不维护 | 说明这张表由谁维护、是否需要审批。 |
| 6 | fld041YOcA | 运营可直接修改 | checkbox(复选框) | — | 勾选表示运营同学可以按常规流程直接修改；未勾选表示需要审批、工程介入或只读。 |
| 7 | fldIe0afUe | 会影响SOP运行配置 | checkbox(复选框) | — | 勾选表示这张表会被导出并编译进 `sop_config.v1`；修改后必须重新 lint、shadow 和 canary。 |
| 8 | fld13fLlbl | 系统会自动写入 | checkbox(复选框) | — | 勾选表示这张表由线上运行链路自动写入，例如事件表、触达记录表；运营同学原则上只读。 |
| 9 | fldh4XoJMC | 建议入口 | text(文本) | plain | 建议运营同学从哪个视图或流程入口查看/维护这张表。 |
| 10 | fldE3Qfgn7 | 怎么维护 | text(文本) | plain | 用自然语言说明这张表能改什么、不能改什么、改动前要做什么校验。 |
| 11 | fldTStcWod | 保留/迁移策略 | text(文本) | plain | 说明这张表是长期保留、逐步替代、兼容旧链路，还是未来可废弃。 |
