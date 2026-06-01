"""AI 工具集 — Function Calling 工具注册与分发"""
from app.tools.inventory_tools import TOOLS as INVENTORY_TOOLS, execute as inventory_exec
from app.tools.sales_tools import TOOLS as SALES_TOOLS, execute as sales_exec
from app.tools.supplier_tools import TOOLS as SUPPLIER_TOOLS, execute as supplier_exec
from app.tools.product_tools import TOOLS as PRODUCT_TOOLS, execute as product_exec
from app.tools.action_tools import TOOLS as ACTION_TOOLS, execute as action_exec
from app.tools.chart_tools import TOOLS as CHART_TOOLS, execute as chart_exec

ALL_TOOLS = INVENTORY_TOOLS + SALES_TOOLS + SUPPLIER_TOOLS + PRODUCT_TOOLS + ACTION_TOOLS + CHART_TOOLS

_EXECUTORS = [inventory_exec, sales_exec, supplier_exec, product_exec, action_exec, chart_exec]


def execute_tool(name: str, arguments: dict, db) -> dict:
    for executor in _EXECUTORS:
        result = executor(name, arguments, db)
        if result is not None:
            return result
    return {"error": f"Unknown tool: {name}"}
