---
name: monitoring-orchestrator
description: 人审运营监控体系·SOP-first 流程编排。Invoke when a configured SOP needs config lint, process artifact validation, report-only/shadow publishing, route preview, or run audit.
metadata:
  version: "0.2.1"
  author: 李中涛
  status: MVP
  tags: [人审运营, 横向能力, SOP, 编排, shadow, report-only, canary]
  requires:
    bins: ["python3"]
    siblings: ["review-monitoring-shared", "anomaly-touch", "owner-routing"]
  requires_optional:
    - "warehouse-skill：用于未来数据就绪 gate 和语义层取数"
    - "lark-*：运行时报告发布或触达所需平台能力，不作为项目内 sibling 上传"
  requires_note: "MVP 支持 manual/report_only/shadow；canary 仅在匹配 production_authorization.v1 文件且限定单 SOP/单等级/单目标时放行。正式事件触达和状态写入在后续阶段启用。"
---

# monitoring-orchestrator — SOP-first 流程编排

## 定位

`monitoring-orchestrator` 是人审运营监控体系的流程权威。MVP 版本默认只做安全的 report-only/shadow 编排；受控 canary 必须提供匹配的 `production_authorization.v1` 授权文件：

1. 读取本地 `sop_config.v1` 配置；
2. 调用 `review-monitoring-shared/scripts/config_linter.py` 做配置校验；
3. 校验 process skill 标准产物目录；
4. 通过 `anomaly-touch` 的 report policy adapter 渲染报告卡片和 publish summary；
5. 可选调用 `owner-routing` 生成 route preview；
6. 写入 `run_summary.json` 和 `run_audit.jsonl`。

## MVP 运行入口

默认入口使用仓库内本地配置，不要求运行时访问飞书多维表格：

```bash
python3 scripts/run_orchestrator.py \
  --config ../review-monitoring-shared/examples/low_efficiency_sop_config.sample.json \
  --sop-id low_efficiency_labeling \
  --run-mode report_only \
  --process-run-dir <analysis_run_dir> \
  --dry-run
```

受控 canary 入口：

```bash
python3 scripts/run_orchestrator.py \
  --config <single-target-canary-config.json> \
  --sop-id low_efficiency_labeling \
  --run-mode canary \
  --process-run-dir <analysis_run_dir> \
  --report-policy-id low_efficiency_p2_detail_report_only \
  --production-authorization-file <production_authorization.v1.json>
```

## 当前边界

- 不取数、不拼 SQL、不判断业务等级。
- 不写事件主表、不写触达记录、不建群、不正式发送 POC 触达。
- `canary` 只允许单 SOP、单 report policy、单等级、单目标用户或测试群的报告发布。
- `active` / `touch_execute` 继续阻断。
- 不把 `P0/P1/P2/notice` 当全局等级，只消费当前 SOP 的等级字典。
- 正式触达必须等 `route_result`、人工确认和卡片安全校验完整后再开启。

## 依赖

- 配置 lint：`../review-monitoring-shared/scripts/config_linter.py`
- 报告发布：`../anomaly-touch/scripts/report_policy.py`
- 路由预览：`../owner-routing/scripts/route_owner.py`
