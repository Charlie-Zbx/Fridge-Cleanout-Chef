from decimal import Decimal
import pytest
from pydantic import ValidationError
from kitchen.domain import Plan, Inventory, StockItem
from kitchen.catalog import recipes, ingredients, validate_inventory
from kitchen.planning import evaluate, search, find_rule_plan


def plan(*ids, servings=1):
    return Plan(meals=[{"dishes":[{"recipe_id":i,"servings":servings}]} for i in ids])


def test_aggregate_stock_shortage(context):
    result=evaluate(plan("cabbage_egg","cabbage_egg"),context)
    assert not result["feasible"]
    egg=next(v for v in result["missing"] if v["ingredient_id"]=="egg")
    assert egg["required"]==4 and egg["available"]==3 and egg["shortage"]==1


def test_exact_remaining(context):
    result=evaluate(plan("cabbage_egg","pan_tofu"),context)
    assert result["feasible"]
    assert result["consumption"]=={"cabbage":100,"egg":2,"tofu":150}
    assert {x["ingredient_id"]:x["quantity"] for x in result["remaining"]}=={"egg":1,"cabbage":100,"tofu":150}


def test_unused_inventory_not_added_to_consumption(context):
    context.preferences.meals=1
    report=evaluate(plan("cabbage_egg"),context)
    assert set(report["consumption"])=={"egg","cabbage"}
    assert next(x for x in report["remaining"] if x["ingredient_id"]=="tofu")["quantity"]==300


@pytest.mark.parametrize("field,value,code",[("equipment",["pot"],"equipment"),("excluded_allergens",["egg"],"allergen"),("excluded_ingredients",["tofu"],"excluded"),("minutes_per_meal",10,"time"),("allow_draft_recipes",False,"unreviewed")])
def test_hard_constraints(context,field,value,code):
    setattr(context.preferences,field,value)
    assert code in {v["code"] for v in evaluate(plan("cabbage_egg","pan_tofu"),context)["violations"]}


def test_two_dishes_time_adds(context):
    context.preferences.meals=1
    result=evaluate(Plan(meals=[{"dishes":[{"recipe_id":"cabbage_egg","servings":1},{"recipe_id":"pan_tofu","servings":1}]}]),context)
    assert result["meals"][0]["minutes"]==33
    assert any(v["code"]=="time" for v in result["violations"])


def test_unknown_recipe_and_wrong_servings(context):
    assert not evaluate(plan("invented","pan_tofu"),context)["feasible"]
    assert any(v["code"]=="servings" for v in evaluate(plan("cabbage_egg","pan_tofu",servings=2),context)["violations"])


def test_pantry_is_not_assumed(context):
    context.inventory.pantry=[]
    assert not evaluate(plan("cabbage_egg","pan_tofu"),context)["feasible"]


def test_rule_solver_feasible(context):
    candidate=find_rule_plan(context)
    assert candidate and evaluate(candidate,context)["feasible"]


def test_units_duplicates_and_nonfinite_rejected():
    with pytest.raises(ValueError):validate_inventory(Inventory(items=[{"ingredient_id":"egg","quantity":3,"unit":"g"}]))
    with pytest.raises(ValueError):validate_inventory(Inventory(items=[{"ingredient_id":"egg","quantity":1.5,"unit":"piece"}]))
    with pytest.raises(ValidationError):Inventory(items=[{"ingredient_id":"egg","quantity":1,"unit":"piece"}]*2)
    with pytest.raises(ValidationError):StockItem(ingredient_id="egg",quantity="NaN",unit="piece")


def test_all_seed_recipes_are_honest_and_resolvable():
    seed=recipes()
    assert len(seed)==30 and len({r.id for r in seed})==30
    assert all(not r.reviewed and r.cooked_count==0 for r in seed)
    assert all(i.ingredient_id in ingredients() and i.unit==ingredients()[i.ingredient_id].unit for r in seed for i in r.ingredients)


def test_soy_sauce_allergen(context):
    context.preferences.excluded_allergens=["wheat"]
    context.preferences.minutes_per_meal=45
    context.preferences.meals=1
    context.inventory.pantry.append("soy_sauce")
    assert any(v["code"]=="allergen" for v in evaluate(plan("pepper_pork"),context)["violations"])
