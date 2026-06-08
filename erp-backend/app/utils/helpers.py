"""工具函数"""


def escape_ilike(value: str) -> str:
    """转义 ilike 查询中的 SQL 通配符 % 和 _"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")