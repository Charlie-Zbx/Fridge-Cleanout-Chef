"""Host-owned portion arithmetic; never infer timing from model prose."""
from decimal import Decimal, ROUND_CEILING
from .domain import Recipe
from .catalog import ingredients


def portion(recipe: Recipe, servings: int) -> dict:
    profile = recipe.serving_profiles.get(str(servings))
    if profile is None:
        if servings > 2:
            raise ValueError("菜谱缺少该人数对应的制作时间与分批说明")
        minutes, batches, instructions = recipe.minutes, 1, "按配方顺序制作；此为旧版时间估计。"
    else:
        minutes, batches, instructions = profile.minutes, profile.batches, profile.instructions
    quantities = []
    for item in recipe.ingredients:
        amount = item.quantity * Decimal(servings) / Decimal(recipe.base_servings)
        amount = amount.to_integral_value(rounding=ROUND_CEILING) if item.unit == 'piece' else amount.quantize(Decimal('.01'), rounding=ROUND_CEILING)
        quantities.append({'ingredient_id':item.ingredient_id,'name':ingredients()[item.ingredient_id].name,'quantity':float(amount),'unit':item.unit})
    return {'servings':servings,'minutes':minutes,'batches':batches,'batch_instructions':instructions,'quantities':quantities}
