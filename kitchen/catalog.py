import json
from functools import lru_cache
from pathlib import Path

from .domain import Ingredient, Recipe, Inventory, Preferences

DATA = Path(__file__).parent / "data"


@lru_cache
def ingredients() -> dict[str, Ingredient]:
    return {x.id: x for x in (Ingredient.model_validate(v) for v in json.loads((DATA / "ingredients.json").read_text(encoding="utf-8")))}


def recipes() -> list[Recipe]:
    return [Recipe.model_validate(v) for v in json.loads((DATA / "recipes.json").read_text(encoding="utf-8"))]


PANTRY = {"oil": "食用油", "salt": "盐", "soy_sauce": "酱油", "vinegar": "醋", "sugar": "糖", "starch": "淀粉"}
PANTRY_ALLERGENS = {"soy_sauce": ["soy", "wheat"]}
EQUIPMENT = {"pan": "平底锅/炒锅", "pot": "汤锅", "steamer": "蒸锅", "rice_cooker": "电饭煲"}
ALLERGENS = {"egg": "蛋", "soy": "大豆", "wheat": "小麦", "milk": "奶", "fish": "鱼", "shellfish": "甲壳类", "peanut": "花生"}


def validate_inventory(inventory: Inventory) -> Inventory:
    for item in inventory.items:
        entry = ingredients().get(item.ingredient_id)
        if not entry:
            raise ValueError(f"未登记的食材：{item.ingredient_id}")
        if entry.unit != item.unit:
            raise ValueError(f"{entry.name}请使用 {entry.unit}，包装数量需先确认换算")
        if item.unit == "piece" and item.quantity != item.quantity.to_integral_value():
            raise ValueError(f"{entry.name}请填写整数个")
    if set(inventory.pantry) - PANTRY.keys():
        raise ValueError("存在未登记的调料")
    return inventory


def validate_preferences(prefs: Preferences) -> Preferences:
    for ids in (prefs.excluded_ingredients, prefs.priority_ingredients):
        if set(ids) - ingredients().keys():
            raise ValueError("偏好中包含未登记食材")
    if set(prefs.equipment) - EQUIPMENT.keys():
        raise ValueError("存在未登记厨具")
    if set(prefs.excluded_allergens) - ALLERGENS.keys():
        raise ValueError("存在未登记忌口类别")
    return prefs
