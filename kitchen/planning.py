from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from itertools import product

from .catalog import ingredients, PANTRY_ALLERGENS, PANTRY, EQUIPMENT
from .domain import Context, Plan, Dish, Meal, Recipe
from .portions import portion


def recipe_issues(recipe: Recipe, context: Context) -> list[dict]:
    p = context.preferences
    issues = []
    def issue(code, message):
        issues.append({"code": code, "message": message, "recipe_id": recipe.id})
    if not recipe.reviewed and not p.allow_draft_recipes:
        issue("unreviewed", f"{recipe.name}尚未人工审核")
    for x in recipe.ingredients:
        if x.ingredient_id in p.excluded_ingredients:
            issue("excluded", f"{recipe.name}含忌口食材{ingredients()[x.ingredient_id].name}")
        if set(ingredients()[x.ingredient_id].allergens) & set(p.excluded_allergens):
            issue("allergen", f"{recipe.name}含已排除的过敏原")
    for item in recipe.pantry:
        if set(PANTRY_ALLERGENS.get(item, [])) & set(p.excluded_allergens):
            issue("allergen", f"{recipe.name}的{PANTRY[item]}含已排除的过敏原")
        if item not in context.inventory.pantry:
            issue("pantry", f"缺少已确认的调料：{PANTRY[item]}")
    for item in recipe.equipment:
        if item not in p.equipment:
            issue("equipment", f"缺少厨具：{EQUIPMENT[item]}")
    return issues


def evaluate(plan: Plan, context: Context, *, check_meal_count: bool = True) -> dict:
    """Pure deterministic validation. Never trusts quantities calculated by a model."""
    p = context.preferences
    by_id = {x.id: x for x in context.recipes}
    inventory = {x.ingredient_id: x for x in context.inventory.items}
    used = defaultdict(Decimal)
    violations = []
    meals = []
    if check_meal_count and len(plan.meals) != p.meals:
        violations.append({"code": "meal_count", "message": f"需要{p.meals}顿饭，收到{len(plan.meals)}顿"})
    for index, meal in enumerate(plan.meals):
        consumption = defaultdict(Decimal)
        minutes = 0
        details = []
        ids = [dish.recipe_id for dish in meal.dishes]
        if len(ids) != len(set(ids)):
            violations.append({"code": "duplicate_dish", "message": "同一顿不能重复添加同一道菜"})
        for dish in meal.dishes:
            recipe = by_id.get(dish.recipe_id)
            if recipe is None:
                violations.append({"code": "unknown_recipe", "message": f"不存在或无权限的菜谱：{dish.recipe_id}"})
                continue
            violations.extend(recipe_issues(recipe, context))
            if dish.servings != p.diners:
                violations.append({"code": "servings", "message": f"{recipe.name}份数须与用餐人数一致"})
            try:
                scaled = portion(recipe, dish.servings)
            except ValueError as error:
                violations.append({'code':'portion_profile','message':str(error),'recipe_id':recipe.id})
                continue
            minutes += scaled['minutes']
            quantities = []
            for x in scaled['quantities']:
                amount = Decimal(str(x['quantity']))
                consumption[x['ingredient_id']] += amount
                used[x['ingredient_id']] += amount
                quantities.append(x)
            details.append({**recipe.model_dump(mode="json"), **scaled, "quantities": quantities})
        if minutes > p.minutes_per_meal:
            violations.append({"code": "time", "meal": index, "message": f"第{index+1}顿顺序制作需约{minutes}分钟，超过{p.minutes_per_meal}分钟限制"})
        meals.append({"index": index, "minutes": minutes, "dishes": details, "consumption": {k: float(v) for k, v in consumption.items()}})
    missing = []
    for key, required in used.items():
        item = inventory.get(key)
        available = item.quantity if item else Decimal(0)
        entry = ingredients()[key]
        if item and item.unit != entry.unit:
            violations.append({"code": "unit", "message": f"{entry.name}库存单位错误"})
        if required > available:
            detail = {"code": "stock", "ingredient_id": key, "name": entry.name, "required": float(required), "available": float(available), "shortage": float(required-available), "unit": entry.unit, "message": f"{entry.name}需要{required}{entry.unit}，库存{available}{entry.unit}"}
            missing.append(detail)
            violations.append(detail)
    remaining = [{"ingredient_id": k, "name": ingredients()[k].name, "quantity": float(v.quantity-used.get(k, Decimal(0))), "unit": v.unit} for k, v in inventory.items()]
    return {"feasible": not violations, "inventory_version": context.inventory.version, "violations": violations, "missing": missing, "consumption": {k: float(v) for k,v in used.items()}, "remaining": remaining, "meals": meals, "priority_usage": {k:round(float(min(used.get(k,Decimal(0)),inventory[k].quantity)/inventory[k].quantity),3) for k in p.priority_ingredients if k in inventory and inventory[k].quantity>0}, "uses_draft_recipes": any(not d["reviewed"] for m in meals for d in m["dishes"])}


def search(context: Context, query: str = "", limit: int = 8, offset: int = 0) -> dict:
    candidates = []
    rejected = []
    reasons = defaultdict(int)
    p = context.preferences
    for recipe in context.recipes:
        one = Plan(meals=[Meal(dishes=[Dish(recipe_id=recipe.id, servings=p.diners)])])
        report = evaluate(one, context, check_meal_count=False)
        if not report['feasible']:
            codes = {v['code'] for v in report['violations']}
            for code in codes:
                reasons[code] += 1
            # Restrict explanations to permitted recipes; do not disclose unreviewed
            # recipe instructions or recommend recipes conflicting with exclusions.
            rejected.append({'recipe_id': recipe.id, 'name': recipe.name,
                             'minutes': report['meals'][0]['minutes'],
                             'violations': report['violations'],
                             'priority_matches': sum(x.ingredient_id in p.priority_ingredients for x in recipe.ingredients)})
        if any(v["code"] != "stock" for v in report["violations"]):
            continue
        priority = sum(x.ingredient_id in p.priority_ingredients for x in recipe.ingredients)
        words = " ".join([recipe.name, *recipe.tags, *[ingredients()[x.ingredient_id].name for x in recipe.ingredients]])
        matched = bool(query and query in words)
        candidates.append({"recipe_id": recipe.id, "name": recipe.name, "minutes": report["meals"][0]["minutes"], "missing": report["missing"], "available_now": report["feasible"], "priority_matches": priority, "query_match": matched})
    candidates.sort(key=lambda x: (len(x["missing"]), -x["priority_matches"], -int(x["query_match"]), x["minutes"], x["recipe_id"]))
    available_total = sum(x['available_now'] for x in candidates)
    examples = [x for x in rejected if not any(v['code'] in ('allergen', 'excluded', 'unreviewed') for v in x['violations'])]
    examples.sort(key=lambda x: (len({v['code'] for v in x['violations']}), -x['priority_matches'], len(x['violations']), x['minutes'], x['recipe_id']))
    diagnostic = {'scope': 'all_recipes_in_confirmed_snapshot', 'recipe_count': len(context.recipes),
                  'available_total': available_total, 'no_single_dish_feasible': available_total == 0,
                  'rejected_recipe_counts': dict(reasons),
                  'blocked_examples': [{k:v for k,v in x.items() if k!='priority_matches'} for x in examples[:2]] if available_total == 0 else []}
    return {"total":len(candidates),"has_more":max(0,offset)+max(1,min(limit,30))<len(candidates),"candidates": candidates[max(0,offset):max(0,offset)+max(1,min(limit,30))], "note": "关键词只影响排序，不改变候选范围。diagnostic统计全库，不是当前页。单菜可行不代表两顿合计可行；必须调用evaluate_plan。开发示例时间未实测。", "diagnostic": diagnostic, "drafts_allowed": p.allow_draft_recipes}


def explain_no_single_dish(context: Context, diagnostic: dict) -> str:
    """Explain a proven empty feasible set; never infer global failure from one plan."""
    count = diagnostic['recipe_count']
    prefix = f'按已确认的{context.preferences.diners}人、每顿{context.preferences.minutes_per_meal}分钟条件，'
    if not count:
        return prefix + '当前菜谱库为空，无法生成可执行计划。请先添加并审核配方。'
    counts = diagnostic['rejected_recipe_counts']
    if counts.get('unreviewed') == count:
        return prefix + '当前菜谱库没有本次允许使用的已审核配方。请先审核配方；系统没有自动放宽审核要求。'
    message = prefix + f'已检查当前库的{count}道配方，没有一道同时满足已确认库存、厨具、忌口、审核状态和时间限制，因此无法组成可执行计划。'
    examples = diagnostic.get('blocked_examples', [])
    if examples:
        details = []
        for example in examples:
            explanation = '；'.join(dict.fromkeys(v['message'] for v in example['violations']))
            details.append(example['name'] + '：' + explanation)
        message += '未通过的例子：' + '；'.join(details) + '。'
    message += '这些是受限制的配方，不是可用候选；程序没有自动改变条件。时间来自当前配方表，开发估计仍需实做验证。'
    return message[:3000]


def find_rule_plan(context: Context, *, exclude: Plan | None = None) -> Plan | None:
    """Explicit non-LLM reference solver for offline previews and evaluation baselines."""
    available = [x["recipe_id"] for x in search(context, limit=30)["candidates"] if x["available_now"]]
    for ids in sorted(product(available, repeat=context.preferences.meals), key=lambda x: -len(set(x))):
        plan = Plan(meals=[Meal(dishes=[Dish(recipe_id=k, servings=context.preferences.diners)]) for k in ids])
        if exclude is not None and plan == exclude:
            continue
        if evaluate(plan, context)["feasible"]:
            return plan
    return None
