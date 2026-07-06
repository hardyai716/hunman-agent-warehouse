# 人审运营 AI 监控体系 · 多 Skill 解耦架构方案

> 目标：把「单体耦合的 human-review-monitoring」重构为「一组职责单一、可插拔、平级协作」的 skill 家族。新增监控业务时只加一块纵向 skill，横向流程零改动。
>
> 状态：**已进入 Claude 三层架构落地**。横向路由/触达已抽离；数据仓库查询层已新增 `warehouse-skill`；效率域已补 `efficiency_domain.md`，低效策略分析已改为 process skill。

---

## 一、问题诊断

现有 `human-review-monitoring` 把两种本质不同的「层」焊死在一个 skill 里：

| 层 | 内容 | 复用性 | 当前状态 |
|---|---|---|---|
| **纵向 · 业务能力** | 「高完审低打标」指标怎么算、怎么分级 | 每个业务不同 | 焊死在监控 skill 里 |
| **横向 · 通用流程** | 感知 → 判断 → 路由 → 触达 → 状态机 | 所有监控业务通用 | 焊死在监控 skill 里 |

**后果**：接入新监控（如审核延时、自动处置准确率）时，触达/路由/状态机这套横向流程要跟着业务重抄一遍，改动面大、易出错、口径漂移。

**已有的正确实践**：`效率模块/low-efficiency-strategy-analysis` 已经把「分析」这块纵向能力单独拆了出来，职责边界写得很干净（「只负责取数→打标率计算→分级，结果如何流转由其他模块负责」）。本方案是把这个思路推广到整个体系。

---

## 二、目标架构：Claude 三层数据分析 + 横向能力 skill

```
不同业务板块SKILL抽象/
├── 效率模块/
│   ├── low-efficiency-strategy-analysis/   ← ✅ 已有（纵向：低效策略分析）
│   └── review-latency-analysis/            ← 未来（纵向：审核延时分析）
├── 质量模块/
│   └── auto-dispose-accuracy-analysis/     ← 未来（纵向：自动处置准确率）
├── 成本模块/
│   └── ...                                 ← 未来
└── 通用能力/                               ← 新增：横向层 + 公共底座
    ├── warehouse-skill/                    ← 数据仓库通用查询层（Semantic Layer first / provenance / validation）
    ├── review-monitoring-shared/           ← 公共底座（配置中心 / schema / 红灯 / 脚本）
    ├── owner-routing/                      ← 横向：责任路由 + SLA
    ├── anomaly-touch/                      ← 横向：触达（建群/卡片/门禁/校验）
    └── monitoring-orchestrator/            ← 横向：编排 + 状态机
```

**物理组织**：所有 skill 平级放（对齐环境里 `lark-*` 家族的约定，不套娃）。业务模块目录（成本/效率/质量）只是**人眼分类**，靠命名和归档区分，不是运行时的嵌套层级。

---

## 三、六类 skill / reference 的职责与边界

### 0. `warehouse-skill`（数据仓库通用查询层）
| 项 | 内容 |
|---|---|
| 职责 | 数据查询通用流程：Semantic Layer first、source tier、fallback reason、freshness、provenance footer、offline eval / online validation |
| 边界 | 不写具体业务分级规则，不替代业务域 reference，不直接做触达/路由 |
| 被谁依赖 | 需要查数的纵向分析 skill |
| 当前产物 | `通用能力/warehouse-skill/SKILL.md`、`references/domain_reference_template.md`、`references/validation_loop.md` |

### 0.1 业务域 reference（Knowledge Skill 文档）
| 项 | 内容 |
|---|---|
| 职责 | 每个业务域的数据 source of truth：canonical metrics、dimensions、segments、governed tables、字段映射、gotchas、troubleshooting |
| 边界 | 不编码完整执行流程，不承担编排 |
| 当前样板 | `通用能力/warehouse-skill/references/efficiency_domain.md` |

### 1. `review-monitoring-shared`（公共底座）
| 项 | 内容 |
|---|---|
| 职责 | 所有监控 skill 共用的**不变资产**：配置中心 base_token、9 张表 schema、等级字典口径、红灯反例黑名单、公共脚本 `card_validator.py`、踩坑清单 `dry_run_pitfalls.md` |
| 边界 | 不含任何业务判断、不含具体指标口径 |
| 被谁依赖 | 所有其他 skill 都 `requires.siblings` 它，正文用 `../review-monitoring-shared/references/xxx.md` 引用 |
| 来源 | 从现有 skill 抽：`base_schema.md`、`card_validator.py`+测试、`dry_run_pitfalls.md`、红灯黑名单 |

### 2. 纵向业务分析 skill（每业务一个）
| 项 | 内容 |
|---|---|
| 职责 | 单一业务流程的**分析过程**：模式选择 → 周期解析 → 语义层发现 → fallback 判定 → SQL 模板执行 → 产出命中清单+证据 |
| 边界 | 只产结论，**不碰路由/触达/状态机** |
| 样板 | `low-efficiency-strategy-analysis`（已改为 process skill） |
| 加新业务 | 先补业务域 reference，再写 process skill；确定性 SQL 放脚本，口径和 gotchas 放 domain reference |

### 3. `owner-routing`（横向：责任路由）
| 项 | 内容 |
|---|---|
| 职责 | 按「指标+等级+范围」匹配责任人/群、算 SLA 截止、解析 open_id/chat_id |
| 边界 | 不判断异常、不发消息；匹配不到标 `missing_route` 转人工 |
| 来源 | 现有 `owner_routing.md` |
| 依赖 | `lark-contact`、`lark-im`、shared |

### 4. `anomaly-touch`（横向：触达）
| 项 | 内容 |
|---|---|
| 职责 | 触达内容生成 + 发送：群聊自主管理（有则复用/无则建群回填）、卡片渲染、幂等查重、**人工确认门禁**、发送前三重硬校验、回写触达记录 |
| 边界 | 不判断异常、不推进状态机（只回写触达记录） |
| 来源 | 现有 `touch_message_writer.md` + `touch_sender.md` + `card_validator.py`（校验逻辑归 shared，调用归这里） |
| 依赖 | `lark-im`、shared |

### 5. `monitoring-orchestrator`（横向：编排 + 状态机）
| 项 | 内容 |
|---|---|
| 职责 | 调度中枢：按业务类型调对应分析 skill → 调 owner-routing → 调 anomaly-touch → 推进事件状态机；结果仲裁、异常降级、多事件并发排序 |
| 边界 | **不写业务判断、不写阈值**；只管流程顺序和状态权威 |
| 来源 | 现有 `flow_orchestration.md` + `flow_manual_run.md` |
| 关键 | 「调哪个分析 skill」是**可插拔配置**——加新业务只在这里登记一行路由，不改代码逻辑 |

---

## 四、协作关系（一轮巡检怎么跑）

```
monitoring-orchestrator（编排 + 状态机）
   │
   │ 1. 按业务类型调纵向分析 skill 取命中清单
   │      ├─ 效率 → low-efficiency-strategy-analysis
   │      ├─ 质量 → auto-dispose-accuracy-analysis（未来）
   │      └─ 成本 → ...（未来，可插拔）
   │ 2. 调 owner-routing → 责任人/群 + SLA
   │ 3. 调 anomaly-touch → 触达（人工确认门禁 + 三重校验）
   │ 4. 推进事件状态机（待判断→待触达→处理中…）
   │
   └ 全程读写 review-monitoring-shared 的配置中心与公共脚本
```

**核心收益**：
- **加新监控业务** = 新写一个纵向分析 skill + 编排层登记一行 → 路由/触达/状态机零改动
- **改进触达逻辑**（如换卡片样式、加校验）= 只改 `anomaly-touch` 一处 → 全业务受益
- **配置/schema 变更** = 只改 `review-monitoring-shared` → 全体一致

---

## 五、依赖声明规范（对齐 lark 家族）

每个 skill 的 `SKILL.md` frontmatter 用 `requires.siblings` 声明横向依赖，正文用相对路径 `../xxx/` 引用，**不复制代码、不物理嵌套**。示例：

```yaml
# monitoring-orchestrator 的 requires
requires:
  siblings:
    - review-monitoring-shared
    - owner-routing
    - anomaly-touch
    - low-efficiency-strategy-analysis   # 可插拔的业务分析 skill
```

---

## 六、迁移步骤（新旧并存，分阶段，不停机）

> 原则：`human-review-monitoring` 作为「参考实现/黄金样板」保留不动，新架构另起炉灶，逐块验证通过后再弃用旧的。

| 阶段 | 动作 | 验证标准 |
|---|---|---|
| **P0 地基** | 建 `review-monitoring-shared`，迁入 base_schema / card_validator+测试 / 红灯黑名单 / dry_run_pitfalls | 单测全绿；一个现有 skill 能通过 `../shared/` 引用跑通 |
| **P1 纵向对齐** | 现有 `low-efficiency-strategy-analysis` 改为 Claude 三层：warehouse-skill + efficiency_domain + process skill | SQL 模板单测全绿；字段映射/gotchas 不在 process skill 重复维护 |
| **P2 横向抽离** | 从 human-review-monitoring 抽出 `owner-routing` 和 `anomaly-touch` 两个独立 skill | 用 low-efficiency 的命中清单，手动串通「分析→路由→触达」一轮 |
| **P3 编排** | 建 `monitoring-orchestrator`，把 P2 的手动串联固化为编排 + 状态机 | 端到端跑通一轮，与旧 skill 结果对齐 |
| **P4 弃旧** | 新链路稳定后，`human-review-monitoring` 标记 deprecated，保留归档 | 新链路承接全部监控业务 |

---

## 七、命名建议

- 前缀统一（便于检索成组）：横向层与 shared 建议放 `通用能力/`，命名不强绑业务
- 纵向业务：`<业务>-analysis`（如 `low-efficiency-strategy-analysis`、`review-latency-analysis`）
- 横向能力：动词/能力名（`owner-routing`、`anomaly-touch`、`monitoring-orchestrator`）
- 公共底座：`review-monitoring-shared`

---

## 八、待你确认的开放问题

1. **业务模块目录 vs 通用能力目录**：横向 skill（路由/触达/编排/shared）是放一个独立的 `通用能力/` 目录，还是平铺在业务模块同级？（本方案默认前者）
2. **是否现在就要动手 P0 地基**，还是先把这份方案定稿、等有第二个业务 skill 时再启动重构？
3. **配置中心 base 是否共用**：新体系是否继续用现有 base_token `<BASE_TOKEN>`，还是各业务模块独立 base？

---

## 九、当前落地状态（2026-07-06）

用户已确认三项决策：

1. 横向 skill 放入独立 `通用能力/` 目录；
2. 先做横向抽离；
3. 配置中心暂时共用同一个 Base（`<BASE_TOKEN>`），真实值放在私有配置或运行环境中，其长期定位后续再定。

### 已完成

| 阶段 | 状态 | 产物 |
|---|---|---|
| P0 地基 | ✅ 已完成 | `通用能力/review-monitoring-shared/`：公共 schema、通用红线、踩坑清单、`card_validator.py` 与 27 个单测 |
| 数据仓库通用层 | ✅ 已完成初稿 | `通用能力/warehouse-skill/`：Semantic Layer first、业务域模板、validation loop、本地 eval 模拟脚本 |
| 效率域 Knowledge Reference | ✅ 已完成初稿 | `通用能力/warehouse-skill/references/efficiency_domain.md`：效率域 canonical metrics、字段映射、样本池、gotchas |
| P1 纵向对齐 · 低效策略 | ✅ 已完成 | `效率模块/low-efficiency-strategy-analysis/SKILL.md` 已改为 process skill；`sql_templates.py` 为确定性 SQL template engine |
| P2 横向抽离 · 责任路由 | ✅ 已完成 | `通用能力/owner-routing/`：责任路由 + SLA 计算横向 skill |
| P2 横向抽离 · 触达 | ✅ 已完成 | `通用能力/anomaly-touch/`：触达生成 + 群聊自主管理 + 人工确认门禁 + 三重硬校验横向 skill |
| P3 编排层 MVP | ✅ 已完成 MVP | `通用能力/monitoring-orchestrator/`：支持 SOP-first config lint、process 产物校验、report-only/shadow 报告发布、route preview 和运行审计；正式事件触达与完整状态机仍在后续阶段 |
