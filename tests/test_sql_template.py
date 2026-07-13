"""包内业务 SQL（`queries/event_api.sql`）的回归测试。

公共参考仓直接收录真实 SQL（无 *.example.* 模板）；这里守护它随 wheel 发布的
占位符 / 转义约定：

1. SQL 能被 importlib.resources 读到（即确实随包分发）。
2. 只用命名占位符 ``%(event_date)s`` / ``%(limit)s``，且没有未转义的裸 ``%``
   —— LIKE 模式里的字面 ``%`` 必须写成 ``%%``，否则 psycopg3 抛 ProgrammingError。
"""
from __future__ import annotations

import importlib.resources
import re


def _sql() -> str:
    """读包内业务 SQL（editable / 已装 wheel 下都解析得到）。"""
    return (
        importlib.resources.files("redshift_mcp_pldemo")
        .joinpath("queries", "event_api.sql")
        .read_text(encoding="utf-8")
    )


def test_sql_resource_loadable() -> None:
    assert _sql().strip()


def test_sql_uses_named_placeholders() -> None:
    sql = _sql()
    assert "%(event_date)s" in sql
    assert "%(limit)s" in sql


def test_no_unescaped_bare_percent() -> None:
    # 去掉合法的 %(name)s 命名占位符与 %% 转义后，不应再有裸 %。
    stripped = re.sub(r"%\([A-Za-z_]\w*\)s", "", _sql()).replace("%%", "")
    assert "%" not in stripped, (
        "SQL 含未转义的裸 '%'；LIKE 模式里的字面量 '%' 必须写成 '%%'。"
    )
