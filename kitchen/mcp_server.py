"""Kitchen MCP Server: only read-only recipe access and deterministic calculations.

Run with `python -m kitchen.mcp_server`. KITCHEN_CONTEXT_FILE is supplied by the
host, not by the model. Each run uses a private, immutable context snapshot.
"""
import os
from pathlib import Path

from fastmcp import FastMCP

from .domain import Context, Inventory, Preferences, Plan
from .catalog import recipes
from .planning import search, evaluate
from .portions import portion


server = FastMCP("Kitchen MCP Server", instructions="菜谱检索与库存约束工具。库存和限制已由宿主确认，不接受模型改写。")


def context() -> Context:
    path = os.environ.get("KITCHEN_CONTEXT_FILE")
    if path:
        return Context.model_validate_json(Path(path).read_text(encoding="utf-8"))
    # Inspector starts with no user's stock and no secrets.
    return Context(inventory=Inventory(), preferences=Preferences(), recipes=recipes())


@server.tool
def search_recipes(query: str = "", limit: int = 8, offset: int = 0) -> dict:
    """检索已确认约束下的候选；query只排序、不扩大范围。diagnostic是全库计数及受阻原因，不受分页影响。缺料会列出；跨餐另行检查。"""
    return search(context(), query[:100], limit, offset)


@server.tool
def get_recipe(recipe_id: str) -> dict:
    """读取基础配方及当前人数的用量、时间、分批说明、步骤、来源与审核状态。"""
    ctx = context()
    recipe = next((r for r in ctx.recipes if r.id == recipe_id), None)
    if recipe is None:
        raise ValueError("不存在的菜谱编号")
    if not recipe.reviewed and not ctx.preferences.allow_draft_recipes:
        raise ValueError("该菜谱尚未审核，本次任务未允许使用开发示例")
    return {**recipe.model_dump(mode="json", exclude={"serving_profiles"}), **portion(recipe, ctx.preferences.diners)}


@server.tool
def evaluate_plan(plan: dict) -> dict:
    """检查候选计划（meals -> dishes -> recipe_id, servings）。由程序计算跨餐用量、剩余、时间与硬条件冲突。库存与要求来自宿主，不能作为参数覆盖。"""
    report = evaluate(Plan.model_validate(plan), context())
    # Full canonical recipes are rendered by the host, not repeated on every model turn.
    report["meals"] = [{"index":m["index"],"minutes":m["minutes"],"consumption":m["consumption"]} for m in report["meals"]]
    return report


if __name__ == "__main__":
    server.run(transport="stdio", show_banner=False)
