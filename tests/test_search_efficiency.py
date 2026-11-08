import asyncio
from decimal import Decimal

import pytest

from kitchen import agent
from kitchen.planning import search
from kitchen.domain import Inventory


@pytest.mark.asyncio
async def test_verified_empty_set_stops_after_one_model_round(context, tmp_path):
    context.preferences.diners = 5
    context.preferences.minutes_per_meal = 20
    for item in context.inventory.items:
        item.quantity = Decimal(20 if item.unit == 'piece' else 1500)
    result = await agent.run_agent(context, '五人每顿只有20分钟', 'empty-verified', checkpoint_path=tmp_path/'check.db')
    assert result['status'] == 'no_plan' and result['plan'] is None
    assert result['termination'] == 'verified_no_single_dish'
    assert result['model_calls'] == 1
    calls = [x for x in result['trace'] if x['kind'] == 'mcp_tool']
    assert len(calls) == 1 and calls[0]['tool'].endswith('search_recipes')
    assert result['diagnostic']['scope'] == 'all_recipes_in_confirmed_snapshot'
    assert '当前库的30道配方' in result['message']
    assert '45分钟' in result['message'] and '20分钟' in result['message']
    assert '不是可用候选' in result['message']


def test_empty_page_is_not_global_no_plan(context):
    page = search(context, offset=10000)
    assert not page['candidates']
    assert page['diagnostic']['available_total'] > 0
    assert not page['diagnostic']['no_single_dish_feasible']
    first = search(context, query='totally different words')
    assert first['diagnostic'] == page['diagnostic']


@pytest.mark.asyncio
async def test_single_dish_feasible_does_not_skip_cross_meal_check(context, tmp_path):
    context.inventory = Inventory(items=[{'ingredient_id':'cabbage','quantity':150,'unit':'g'}], pantry=['oil','salt'])
    assert search(context)['diagnostic']['available_total'] > 0
    result = await agent.run_agent(context, '两顿饭不能重复占用库存', 'aggregate-shortage', checkpoint_path=tmp_path/'check.db')
    assert result['status'] == 'no_plan'
    assert result.get('termination') != 'verified_no_single_dish'
    assert any(x['kind']=='mcp_tool' and x['tool'].endswith('evaluate_plan') and not x['result']['feasible'] for x in result['trace'])


def test_stock_shortage_and_review_block_are_explained(context):
    context.inventory.items[0].quantity = Decimal(0)
    context.inventory.items[1].quantity = Decimal(1)
    context.inventory.items[2].quantity = Decimal(1)
    result = search(context)
    assert result['candidates'] and not any(x['available_now'] for x in result['candidates'])
    assert result['diagnostic']['no_single_dish_feasible']
    assert result['diagnostic']['rejected_recipe_counts']['stock'] > 0
    context.preferences.allow_draft_recipes = False
    diagnostic = search(context)['diagnostic']
    assert not diagnostic['blocked_examples']
    assert '已审核配方' in agent.explain_no_single_dish(context, diagnostic)


@pytest.mark.asyncio
async def test_memo_deduplicates_concurrent_calls_and_is_snapshot_local():
    calls = []
    async def execute():
        calls.append(1)
        await asyncio.sleep(0)
        return {'candidates': [1]}, 'origin-id'
    memo = agent.ToolMemo()
    first, second = await asyncio.gather(memo.invoke('search_recipes', {}, execute), memo.invoke('search_recipes', {'query':'','limit':8,'offset':0}, execute))
    assert len(calls) == 1
    assert sorted([first[1], second[1]]) == [False, True]
    assert first[2] == second[2] == 'origin-id'
    await agent.ToolMemo().invoke('search_recipes', {}, execute)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_failed_tool_result_is_not_cached():
    calls = []
    async def failed():
        calls.append(1)
        raise ValueError('tool failed')
    memo = agent.ToolMemo()
    for _ in range(2):
        with pytest.raises(ValueError):
            await memo.invoke('get_recipe', {'recipe_id':'missing'}, failed)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_real_mcp_duplicate_is_recorded_as_cache_not_extra_mcp(context, tmp_path, monkeypatch):
    original = agent.OfflineModel
    class RepeatedSearch(original):
        def _generate(self, *args, **kwargs):
            phase = self._phase
            result = super()._generate(*args, **kwargs)
            if phase == 0:
                result.generations[0].message.tool_calls.append(self._call('search_recipes', {'limit':30}))
            return result
    monkeypatch.setattr(agent, 'OfflineModel', RepeatedSearch)
    result = await agent.run_agent(context, '安排两顿', 'memo-integration', checkpoint_path=tmp_path/'check.db')
    assert result['status'] == 'ready'
    actual = [x for x in result['trace'] if x['kind']=='mcp_tool' and x['tool'].endswith('search_recipes')]
    cached = [x for x in result['trace'] if x['kind']=='tool_cache']
    assert len(actual) == 1 and len(cached) == 1
    assert cached[0]['source_event_id'] == actual[0]['event_id']
