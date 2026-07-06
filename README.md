# 人审数据自动化 IDA Skill 仓库

本仓库用于维护人审运营 AI 监控体系的多 Skill 架构，当前核心方向是基于 Claude 风格三层 Agentic Analytics 架构拆分能力：

- `通用能力/`：横向能力层与公共底座，包括数据仓库查询、责任路由、异常触达等。
- `效率模块/`：纵向业务流程 skill，目前包含低效策略分析。
- `质量模块/`、`成本模块/`：预留业务分类目录。
- `.trae/specs/`：Ralph Loop 规格、任务、验收与进度记录。
- `tools/`：Agent 平台上传包构建工具与 manifest。

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
