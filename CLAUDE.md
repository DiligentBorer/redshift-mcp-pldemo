# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 这是什么

`redshift-mcp` 的**业务插件参考仓**（公开）。对外只提供一个 MCP 工具 `query_event_api_by_date`：
按日期在 Amazon Redshift 上跑一段固定 SQL，返回 IP 维度的 API 命中统计。本仓不是独立可部署物，
而是以 wheel 装进已有 host（`redshift-mcp`）venv、由 host 在运行期加载的**插件包**。

## 常用命令

```bash
uv sync                         # 拉依赖（薄 SDK 走 [tool.uv.sources] 的 git tag，其余走 PyPI）
uv run pytest                   # 全部离线单测，期望 20 passed
uv run pytest tests/test_sql_template.py::test_no_unescaped_bare_percent   # 跑单条
uv build                        # 打 wheel/sdist；config.yaml + queries/*.sql 会被打进包
uv sync --extra standalone      # 额外拉 host，用于本地起真实 server
uv run redshift-mcp --list-plugins            # 验证 entry-point 被发现：应列出 pldemo
uv run redshift-mcp --config dev/config.yaml  # 起本地 MCP server 连真实 Redshift
```

本仓无 lint/format 配置；无 CI。`uv.lock`、`dist/`、`.venv/`、`dev/config.yaml` 均 gitignored。

## 架构要点（读多个文件才能看清的部分）

**依赖形态 —— 只依赖薄契约层，不碰 host 源码。** 生产依赖面仅 `redshift-mcp-sdk`（薄叶子包，
提供 `PluginContext` + errors）。代码只 `from redshift_mcp_sdk import PluginContext`,**绝不 import
`redshift_mcp.*`(host 实现)**。完整 host 只是 `[standalone]` 可选 dev 依赖,不进生产 wheel 的
`Requires-Dist`。改动时务必守住这条边界:任何对 host 内部的直接引用都是架构违规。

**插件契约(三步,见 [`__init__.py`](src/redshift_mcp_pldemo/__init__.py))。**
1. [`pyproject.toml`](pyproject.toml) 声明 entry-point `[project.entry-points."redshift_mcp.plugins"] pldemo = "redshift_mcp_pldemo:register"`,host 用 `importlib.metadata` 自动发现。
2. 暴露 `register(ctx: PluginContext) -> None`。
3. 在 `register` 内用 `ctx.mcp.tool()` 注册工具,闭包捕获 `ctx` 拿共享资源。

**运行期一律走 ctx,不硬编码、不自建。** DB 执行用 `ctx.aexecute`(host 已封装计时/行截断/审计),
异常包装用 `ctx.db_errors`(注入 request_id、不吞编程错误),插件自名取 `ctx.plugin_name`(entry-point
名),logger 取 `ctx.logger.getChild(ctx.plugin_name)`。[`query.py`](src/redshift_mcp_pldemo/query.py)
里的 `run_query` 是「插件自管连接池」的**备选参考实现,未接线**——别误以为它是主路径。

**配置内聚 —— host 不参与,插件自解析(见 [`_config.py`](src/redshift_mcp_pldemo/_config.py))。**
查询 SQL 不硬编码进代码,由插件自带的 `config.yaml` 提供(`sql` 内联 / `sql_file` 相对配置目录,
二选一,pydantic 强制恰好其一)。解析优先级:**显式 path(测试用)> 环境变量
`REDSHIFT_MCP_PLDEMO_CONFIG` > 包目录内默认 `config.yaml`**。找不到直接抛 `FileNotFoundError`(带修复
指引),**绝不回落范本兜底**——由 host 的 `load_plugins` try/except 隔离、跳过本插件,不搞崩 server。

**两份 config.yaml 语义完全不同,别混。**
- [`src/redshift_mcp_pldemo/config.yaml`](src/redshift_mcp_pldemo/config.yaml):插件自有业务配置(SQL 来源),随 wheel 分发、入库。
- `dev/config.yaml`:standalone runner 的 **host 侧**配置(连接串/`auth_token` 等密钥),gitignored;
  仓库里只有占位模板 [`dev/config.dev.yaml`](dev/config.dev.yaml),用时 `cp` 一份填真值。

## SQL 约定

`queries/event_api.sql` 只用命名占位符 `%(event_date)s` / `%(limit)s`;`limit` 由工具传
`max_rows + 1`,用于服务端截断判断(返回行数 > `max_rows` 则标 `truncated`)。SQL 里任何字面 `%`
(如 LIKE 模式)必须写成 `%%`,否则 psycopg3 抛 `ProgrammingError`——`test_sql_template.py` 会守护这点。

## 命名一致性(易踩坑)

工具名 `query_event_api_by_date` 与 SQL 文件 `queries/event_api.sql` 必须在**所有**文件里保持一致
(代码 / 测试断言 / config.yaml 的 `sql_file` / pyproject description / README / docstring)。历史上出现
过半途改名(`error`↔`event`、`timeout_api`↔`event_api`)导致测试全线崩。改名时用 grep 全仓一次性替换。
