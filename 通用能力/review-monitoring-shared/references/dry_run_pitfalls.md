# dry_run_pitfalls — 跑批踩坑规避清单 + 前置 checklist

> 来源：2026-07-03 首次端到端干运行（id3, run_date=2026-07-02）实测复盘。本文把当次踩到的 9 类坑固化为「规避动作」，并给出跑批前的固化 checklist。正式跑批/迭代前对照本表，避免重复踩坑。
>
> **过期条件**：MVP 稳定、跑批脚本内建这些 gate 后，本文并入 flow_orchestration 运维章节。

## 一、工具链与环境

| # | 坑 | 规避动作 |
|---|---|---|
| 1 | `bytedcli` 版本过旧（沙盒预装 0.73.0 无 `aeolus` 子命令，报 `unknown command 'aeolus'`） | 跑批前 `bytedcli --version` 校验；低于 0.90 先 `NPM_CONFIG_REGISTRY=http://bnpm.byted.org npm i -g @bytedance-dev/bytedcli@latest` 升级。把版本检查写进 run 脚本前置 gate |
| 2 | 找不到独立 `lark-cli` 二进制 | 飞书能力已并入 `bytedcli lark` 子命令（`bytedcli lark base/im/...`）；也可能是独立 `@larksuite/cli`。以环境实际可用为准，不硬找某一形态 |
| 3 | `-j/--json` 位置错误（`bytedcli aeolus query -j ...` 报 `unknown command`） | `-j` 是**全局参数**，必须放在 `bytedcli` 之后、子命令之前：`bytedcli -j aeolus query ...` |
| 3b | 🔴 **IDA/Agent 沙盒锁定官方 iDA 机器人身份，无法切自定义机器人**：沙盒的飞书凭证由外部注入（`LARKSUITE_CLI_APP_ID=<APP_ID>`=官方 iDA），`bytedcli lark config/profile/auth/login` 均返回「credentials are provided externally and do not support interactive management」，环境变量覆盖也无效 | **这是平台环境限制，非配置问题，改代码/配置解决不了**。取舍：① 接受用官方 iDA 身份发送（发送方显示 iDA，全流程可跑）；② **发送环节挪到能自主配置 lark-cli 的本地/独立环境**执行（用自定义机器人，发送方显示自己），IDA 只负责取数/判断/渲染（推荐，实测跑通）。**不要把 app_secret/tenant_access_token 塞进沙盒**（安全风险高，且沙盒未必认） |
| 3c | 🔴 **沙盒 strict-mode=user，bot 身份被禁 + user 缺 im 权限，两头堵**：`--as bot` 报「strict mode is "user", only user-identity commands are available」；退回 user 身份发交互卡片报 `230027 user_unauthorized`；想 `config strict-mode off` 解除又被「externally provided, not support interactive management」拦住（与 #3b 同源硬锁） | 确认沙盒无法改 strict-mode 后**不要再折腾**，直接走 #3b 方案②：发送环节挪本地。本地 lark-cli（strict-mode=off、能自主 config init）配自定义机器人即可发送。让 IDA 命中硬锁后如实停止，不绕过门禁、不塞 token |
| 3d | 🔴 **open_id 跨应用隔离**：同一个人（李中涛）在不同飞书应用下的 open_id 不同——官方 iDA 应用是 `ou_9c2344df…`，自定义机器人应用是 `ou_0a3167c1…`。用 A 应用的 open_id 让 B 应用发消息，报 `99992361 open_id cross app` | **open_id 必须用「发送应用视角」的值**。最稳的解析法：读目标群成员列表 `bytedcli lark im chat.members get --chat-id <oc_> --as bot`（用发送机器人身份），拿到的成员 open_id 就是该应用视角下的正确值。不要跨应用复用 open_id；跨应用统一用户身份应改用 `union_id` |

## 二、风神取数与 SQL

| # | 坑 | 规避动作 |
|---|---|---|
| 4 | 字段引用写法反复试错（裸 `[中文名]` 报 `Unrecognized token '['`；纯反引号 `` `中文名` `` 报未知表） | 物理表 FROM 下语义字段一律用 `` `[Name]` ``（反引号+方括号），由风神服务端展开成底层表达式；物理英文列裸写。Name 取自 `dataset-fields` 的 **Name 列**（非中文 description）。详见 metric_data_fetcher 的 A 段 |
| 5 | 逻辑表名 `FROM \`<datasetId>\`` 报 `未知表`；`FROM \`[数据集名]\`` 报字段权限 | 固定走「`resolve-report`（若给URL）→ `dataset-fields` → `dataset-model-info` 拿物理表 `db.table` → 物理表 SQL」四步；物理表名裸写不加反引号，不用 datasetId 当表名 |
| 6 | `query-editor query parse` 因 Query Editor 对物理表无 SELECT 权限返回 `LACK_PERMISSION` | parse **不能作为硬门禁阻断流程**；失败时降级为 `LIMIT 1` 小样本探测验证可执行性，通过后再跑全量。**禁止跳过预校验直接跑全量**（违反反例黑名单第3条） |

## 三、输出解析（本次最严重）

| # | 坑 | 规避动作 |
|---|---|---|
| 7 | 文本表格输出截断 reason（默认截 24 字符加 `...`），前缀相同的不同 reason 被误判重复，叠加分页/空行/`Total:` 干扰行，位置解析器出错，notice 从真实 394 算成 381 | **所有取数命令一律加 `-j` 走 JSON 输出**，直接读 `data.columns`+`data.rows`，彻底废弃文本表格解析。**这是本次最值得固化的一条** |
| 8 | `--limit` 默认 100 导致分页（394 行被截成 100 + 分页提示，解析器误把第二页当新表） | 所有查询显式传 `--limit 1000`（或按规则预估上限+1），并检查返回的 `truncated` 字段，为 `true` 时分页或放大 limit |

## 四、流程与配置

| # | 坑 | 规避动作 |
|---|---|---|
| 9 | 责任路由表「群聊ID」字段为空（4 条路由都没填，实发无法建群/发群） | 实发前加「路由完整性校验」gate——主负责人 open_id、群聊 chat_id 任一为空就标 `missing_route` 转人工，不进入触达发送 |
| — | 读多维表格：`bytedcli lark base +record-list` 不支持 `--json`，用 `--format json`；部分命令只出 Markdown | 读配置表用 `--format json`（若支持）；只出 Markdown 的命令直接解析 Markdown（列数固定、无长文本截断问题，可接受）。大量记录考虑 `+data-query` 聚合 |

## 五、跑批前固化 checklist

按顺序过 gate，任一不过则停：

1. **环境 gate**：`bytedcli --version` ≥ 0.90；`bytedcli lark auth status` / `bytedcli auth status` 已登录；`bytedcli aeolus` 子命令可用。
2. **配置 gate**：6 张配置表全部读取成功；启用的指标 ≥ 1；每条启用路由的主负责人 open_id / 群聊 chat_id 非空（否则标 `missing_route`）。
3. **数据 gate**：目标分区（D-N）`SELECT count() FROM <物理表> WHERE p_date=?` 返回 > 0；未到位直接停，不误报。
4. **SQL gate**：模板渲染通过（`validate_params`+`render_sql`）；先 `LIMIT 1` 探测无语法错误/字段可解析，再跑全量。
5. **取数规范**：所有 `aeolus query` 一律 `bytedcli -j aeolus query ... --limit 1000`，用 JSON 解析，禁止解析文本表格。
6. **字段规范**：语义字段用 `` `[Name]` ``（反引号+方括号），物理英文列裸写；物理表名来自 `dataset-model-info`，不猜。
7. **dry_run 契约**：不写事件表/触达记录表/数据源就绪状态、不调发送接口、不建群；只产出 SQL、命中结果、卡片预览三样本地产物（边界见 flow_manual_run 的「干运行（dry_run）契约」）。
8. **人工确认门禁**：P0/P1/P2/notice 按等级字典表「是否需要人工确认=true」，先 preview 到私聊，收到「确认发送」再实发。
