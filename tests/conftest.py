import os
from pathlib import Path
import pytest
from kitchen.catalog import recipes
from kitchen.domain import Context, Inventory, Preferences


@pytest.fixture(autouse=True)
def no_live(monkeypatch, tmp_path):
    monkeypatch.setenv("KITCHEN_ENABLE_LIVE","0")
    monkeypatch.delenv("DEEPSEEK_API_KEY",raising=False)
    monkeypatch.setenv("KITCHEN_DATA_DIR",str(tmp_path/"data"))
    monkeypatch.setenv("LANGSMITH_TRACING","false")
    monkeypatch.setenv("LANGCHAIN_TRACING_V2","false")


@pytest.fixture
def context():
    return Context(inventory=Inventory(items=[{"ingredient_id":"egg","quantity":3,"unit":"piece"},{"ingredient_id":"cabbage","quantity":200,"unit":"g"},{"ingredient_id":"tofu","quantity":300,"unit":"g"}],pantry=["oil","salt"]),preferences=Preferences(priority_ingredients=["cabbage"],allow_draft_recipes=True),recipes=recipes())
