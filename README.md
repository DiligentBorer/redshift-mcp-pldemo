# redshift-mcp-pldemo

[`redshift-mcp`](https://github.com/DiligentBorer/redshift-mcp) 的**业务插件**（公共参考仓），
提供 `query_event_api_by_date` 工具：在 Amazon Redshift 上跑一段固定 SQL，返回 IP 维度的
API 命中统计。

## 依赖形态：只依赖薄契约层 SDK，不引入 host 源码

```
redshift-mcp-sdk   ← 薄契约叶子包（PluginContext + errors）
   ↑                        ↑
redshift-mcp (host)     redshift_mcp_pldemo（本仓）
                            生产依赖：仅 redshift-mcp-sdk
                            [standalone] 可选依赖：redshift-mcp（仅本地 runner 用）
```

- **生产依赖面只有 `redshift-mcp-sdk`**：代码只 `from redshift_mcp_sdk import PluginContext`，
  不 import 任何 `redshift_mcp.*`（host 实现）。运行期由 host 加载本插件并注入 `PluginContext`。
- 完整 host 仅作**可选 dev 依赖**（`[standalone]` extra），专供本地 runner，不进生产 wheel 的
  `Requires-Dist`。

依赖解析走**公开 Git URL + 固定 tag**（见 `pyproject.toml` 的 `[tool.uv.sources]`，无需私有 PyPI）；
`[tool.uv.sources]` 只作用开发期解析、不写进 build 出的 wheel 元数据。迁到私有 PyPI 时删掉该段、
代码零改动。

## 插件契约

1. `pyproject.toml` 声明 entry-point（让 host 通过 `importlib.metadata` 自动发现）：

   ```toml
   [project.entry-points."redshift_mcp.plugins"]
   pldemo = "redshift_mcp_pldemo:register"
   ```

2. 暴露 `register(ctx: PluginContext) -> None` 入口，在其中用 `ctx.mcp.tool()` 注册工具，
   闭包捕获 `ctx` 拿共享资源（连接池 / config / logger / request_id）。

`PluginContext` 由薄 SDK `redshift_mcp_sdk` 提供，是稳定的公开契约。

## 插件自有配置（约定 + env var）

查询 SQL **不硬编码进包**，由插件**自带的 `config.yaml`** 提供（结构与 host `config.yaml` 同构）。
host 不参与（插件配置内聚原则）：插件按以下优先级自行解析（见 `_config.py`），**找不到则报错跳过、
不静默兜底**：

1. 环境变量 `REDSHIFT_MCP_PLDEMO_CONFIG` 指向的文件；
2. 默认约定：插件包目录内的 `config.yaml`（`<包目录>/config.yaml`）。

配置支持 `sql`（内联）或 `sql_file`（相对配置文件目录），二选一。**公共参考仓直接收录真实
`config.yaml` / `queries/*.sql`**（无 `*.example.*` 模板），它们作为包目录下的普通文件随 wheel 分发，
默认路径即命中。唯一不入库的是 `dev/config.yaml`（standalone runner 的 host 配置，含连接串 /
`auth_token` 等密钥 → `.gitignore`）。

## 单独跑

### ① 离线单测（不连 DB、不需 host runtime，只依赖薄 SDK）

```bash
uv sync          # 从 git 按 [tool.uv.sources] 的 tag 拉 redshift-mcp-sdk 本地构建装入（其余依赖走 PyPI）
uv run pytest    # 日期校验 / SQL 模板 / 配置解析优先级，全程离线；期望 20 passed
```

> **前提**：能对 `github.com` 做 SSH、且 `[tool.uv.sources]` pin 的 tag 已在 host 仓推送——`uv sync` 日志会显示
> `redshift-mcp-sdk==<ver> (from git+ssh://...@<sha>#subdirectory=sdk)`。单测用 `SimpleNamespace` 替身满足
> `PluginContext.config` 契约，**不装完整 host、不连 DB**。

### ② 本地 MCP server（连真实 Redshift，复用 host 启动逻辑）

装 `[standalone]` extra 后，本插件 editable 装进本仓 venv，entry-point 被 host 的 `redshift-mcp`
自动发现 —— 直接复用 host 的 `server.main()`，不在本仓重实现 host：

```bash
uv sync --extra standalone                     # 额外从 git 拉 host
uv run redshift-mcp --list-plugins             # 快速验证:应列出  pldemo   redshift-mcp-pldemo <ver>
cp dev/config.dev.yaml dev/config.yaml         # 填 Redshift 连接 + auth_token（gitignored）
# 插件自有 config.yaml / queries/*.sql 已在仓库里，无需再拷贝
uv run redshift-mcp --config dev/config.yaml   # 起 server：query_event_api_by_date 即在 list_tools
```

用 MCP client 调 `query_event_api_by_date`：合法日期返回结果、非法日期报中文格式错误。（起本地 server
直接用 host 的 `redshift-mcp` console_script 即可，本仓不再包 runner 脚本。）跑完清理生成物：
`rm -rf .venv uv.lock dist .pytest_cache`（都不入库）。

## 构建 / 生产安装

```bash
# 真实 config.yaml / queries/*.sql 已在包目录里，直接打包即随 wheel 分发
uv build
unzip -l dist/redshift_mcp_pldemo-*.whl | grep -E 'config\.yaml|queries/'   # 校验:应含 config.yaml + queries/*.sql
# 装进已装 host 的 venv；生产 wheel 的 Requires-Dist 只有 redshift-mcp-sdk（host venv 里已满足）
uv pip install dist/redshift_mcp_pldemo-*.whl
```

装好后启动 `redshift-mcp`，靠 entry_points 自动发现加载，**不需要改 host 的任何配置**。

## 临时禁用

host `config.yaml` 里：

```yaml
plugins:
  disabled: ["pldemo"]
```

## 版本兼容

本插件与 host 共享同一份 `redshift-mcp-sdk`（一个 venv 只有一个 SDK 版本）。两边都钉
`redshift-mcp-sdk>=0.3,<1.0`（下限 + 次主版本上限，SDK 主版本内严格向后兼容）：resolver 求交集、
SDK 只上浮到兼容最新版，不兼容在**安装期**即暴露，不会在运行期静默踩坑。
