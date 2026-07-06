# 人审数据自动化 IDA Skill 仓库

本仓库用于维护人审运营 AI 监控体系的多 Skill 架构，当前核心方向是基于 Claude 风格三层 Agentic Analytics 架构拆分能力：

- `通用能力/`：横向能力层与公共底座，包括数据仓库查询、责任路由、异常触达、SOP 编排等。
- `效率模块/`：纵向业务流程 skill，目前包含低效策略分析。
- `质量模块/`、`成本模块/`：预留业务分类目录。
- `.trae/specs/`：Ralph Loop 规格、任务、验收与进度记录。
- `tools/`：Agent 平台上传包构建工具与 manifest。

## 当前 Skill 模块

当前交付范围包含 6 个可上传 Skill：

- `review-monitoring-shared`：共享校验、配置 lint、卡片校验与公共契约。
- `warehouse-skill`：离线评估与数据仓库查询能力封装。
- `owner-routing`：按业务对象粒度解析负责人并输出 `route_result`。
- `monitoring-orchestrator`：SOP-first 编排、shadow/report-only 运行与审计输出。
- `anomaly-touch`：报告发布、卡片渲染与触达策略执行入口。
- `low-efficiency-strategy-analysis`：低效策略分析 process skill。

外部平台能力如 `lark-*`、`sqless`、`bytedcli`、`bytedance-aeolus` 只作为运行时依赖或可选能力引用，不作为本项目上传包内的 sibling skill 交付。

## 最终验收

上传到 Agent 平台前，先运行最终验收命令：

```bash
python3 tools/verify_project_ready.py
```

该命令串联 13 个检查项：

- SQL 模板
- 卡片校验
- 配置 lint
- owner-routing
- report publisher
- orchestrator 单测
- warehouse offline eval
- 低效策略 smoke
- orchestrator shadow CLI
- 打包
- zip 审计
- orchestrator live-mode guard
- 生产化预检

验收通过后会生成机器可读摘要：

```text
dist/final_acceptance/acceptance_summary.json
```

上传前必须确认摘要中的 `status` 为 `passed`。每次验收的临时产物会写入 `dist/final_acceptance/tmp/<timestamp>/`。

生产化预检也可以单独运行：

```bash
python3 tools/verify_production_readiness.py
```

在 Ralph Loop Round 5 实现过程中，`tasks.md` / `checklist.md` 里 Task 18-21 的未勾选项可用临时豁免参数验证本地交付物：

```bash
python3 tools/verify_production_readiness.py --allow-open-round5
```

最终验收内部会使用 `--allow-open-round5 --summary-out dist/final_acceptance/tmp/<timestamp>/readiness_summary.json`，并把 readiness summary 记录到 `acceptance_summary.json`。

## 离线安全边界

最终验收按离线安全口径运行：

- 不向 Lark / 飞书发送消息或卡片。
- 不写事件主表或正式触达记录。
- 不覆盖 baseline fixture 或历史分析结果。
- shadow CLI 使用 dry-run 与 route preview，只生成本地审计、对比和报告预览产物。
- 临时运行产物统一落在 `dist/final_acceptance/tmp/<timestamp>/`。
- `canary` / `active` / `touch_execute` 当前 MVP 默认由 live-mode guard 阻断；最终验收会用 `canary --dry-run` 验证该阻断返回非 0 且包含生产授权提示。
- 真实 Lark / Aeolus 副作用、Agent 平台上传动作和生产事件写入仍需平台侧凭证、生产配置校验与人工开关，不由本地 MVP 自动启用。

## 打包

上传到 Agent 平台前，运行：

```bash
python3 tools/package_agent_skills.py
```

生成产物位于：

```text
dist/agent_upload/zips/
```

`dist/` 是可再生成目录，不纳入 Git 版本管理。

主要交付产物：

- `dist/agent_upload/zips/*.zip`：6 个单 Skill 上传包。
- `dist/final_acceptance/acceptance_summary.json`：最终验收摘要。
