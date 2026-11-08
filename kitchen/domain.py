from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Unit = Literal["g", "ml", "piece"]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Ingredient(Model):
    id: str
    name: str
    unit: Unit
    allergens: list[str] = []
    aliases: list[str] = []


class StockItem(Model):
    ingredient_id: str = Field(min_length=1, max_length=60)
    quantity: Decimal = Field(ge=0, le=100000, decimal_places=2)
    unit: Unit


class Inventory(Model):
    items: list[StockItem] = Field(default_factory=list, max_length=80)
    pantry: list[str] = Field(default_factory=list, max_length=30)
    version: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def no_duplicates(self):
        ids = [x.ingredient_id for x in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("同一种食材只能有一条库存，请合并数量")
        if len(set(self.pantry)) != len(self.pantry):
            raise ValueError("常备调料不能重复")
        return self


class Preferences(Model):
    diners: Literal[1, 2, 3, 4, 5] = 1
    meals: Literal[1, 2] = 2
    minutes_per_meal: int = Field(default=20, ge=5, le=120)
    equipment: list[str] = Field(default_factory=lambda: ["pan"], max_length=10)
    excluded_ingredients: list[str] = Field(default_factory=list, max_length=80)
    excluded_allergens: list[str] = Field(default_factory=list, max_length=20)
    priority_ingredients: list[str] = Field(default_factory=list, max_length=20)
    taste: str = Field(default="清淡", max_length=300)
    allow_draft_recipes: bool = False

    @field_validator('diners',mode='before')
    @classmethod
    def integer_diners(cls,value):
        if type(value) is not int: raise ValueError('人数必须是1–5的整数')
        return value


class RecipeIngredient(Model):
    ingredient_id: str
    quantity: Decimal = Field(gt=0, le=100000, decimal_places=2)
    unit: Unit


class ServingProfile(Model):
    minutes: int = Field(gt=0, le=300)
    batches: int = Field(ge=1, le=10)
    instructions: str = Field(max_length=800)


class Recipe(Model):
    id: str
    name: str
    ingredients: list[RecipeIngredient]
    pantry: list[str]
    equipment: list[str]
    minutes: int = Field(gt=0)
    steps: list[str]
    tags: list[str] = []
    source_label: str = "AI 起草的开发示例，未实做"
    source_url: str | None = None
    reviewed: bool = False
    reviewed_at: str | None = None
    cooked_count: int = 0
    base_servings: int = Field(default=1, ge=1, le=5)
    count_rounding: Literal["ceil"] = "ceil"
    serving_profiles: dict[str, ServingProfile] = {}
    version: int = Field(default=1, ge=1)
    team_reviewed: bool = False
    team_reviewed_by: str | None = None
    team_reviewed_at: str | None = None
    cooking_records: list[str] = []


class Dish(Model):
    recipe_id: str
    servings: Literal[1, 2, 3, 4, 5]

    @field_validator('servings',mode='before')
    @classmethod
    def integer_servings(cls,value):
        if type(value) is not int: raise ValueError('份数必须是1–5的整数')
        return value


class Meal(Model):
    dishes: list[Dish] = Field(min_length=1, max_length=3)


class Plan(Model):
    meals: list[Meal] = Field(min_length=1, max_length=2)


class Context(Model):
    inventory: Inventory
    preferences: Preferences
    recipes: list[Recipe]


class AgentAnswer(Model):
    status: Literal["ready", "needs_input", "no_plan"]
    message: str = Field(max_length=3000)
    plan: Plan | None = None

    @model_validator(mode="after")
    def ready_needs_plan(self):
        if self.status == "ready" and self.plan is None:
            raise ValueError("ready 必须包含计划")
        if self.status != "ready" and self.plan is not None:
            raise ValueError("未完成时不能附带可执行计划")
        return self
