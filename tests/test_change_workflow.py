import json

import pytest

from scripts.verify_changes import BatchBudget, specification, workflow


def test_budget_blocks_stage_overrun_and_automatic_repeat(tmp_path):
    spec = specification()
    assert sum(spec['limits'].values()) == spec['max_requests'] == 21
    budget = BatchBudget(tmp_path, spec['limits'])
    for stage, limit in spec['limits'].items():
        budget.enter(stage)
        for _ in range(limit):
            budget.charge()
        with pytest.raises(PermissionError):
            budget.charge()
        with pytest.raises(PermissionError):
            budget.enter(stage)
    assert sum(budget.counts.values()) == 21
    assert json.loads((tmp_path / 'budget.json').read_text())['total_attempts'] == 21


@pytest.mark.asyncio
async def test_continuous_changes_through_real_mcp_offline(tmp_path):
    spec = specification()
    budget = BatchBudget(tmp_path, spec['limits'])
    results = await workflow(tmp_path, 'offline', budget, spec)
    runs = [x for x in results if 'revision' in x]
    assert [x['revision'] for x in runs] == [1, 2, 3]
    assert [x['status'] for x in runs] == ['ready', 'ready', 'no_plan']
    assert len({x['id'] for x in runs}) == 1
    assert sum(budget.counts.values()) == 0
    for stage in ['people', 'time']:
        state = json.loads((tmp_path / (stage + '_intake-state.json')).read_text(encoding='utf-8'))
        assert state['inventory_unchanged'] and state['old_plan_status'] == 'needs_input'
        assert state['after']['excluded_allergens'] == ['shellfish']
        assert state['after']['excluded_ingredients'] == ['shrimp']
        assert state['after']['priority_ingredients'] == ['cabbage']
        assert state['after']['equipment'] == ['pan']
        assert state['after']['meals'] == 2
    five = json.loads((tmp_path / 'people_replan.json').read_text(encoding='utf-8'))
    for meal in five['validation']['meals']:
        assert meal['minutes'] <= 90
        assert all(d['servings'] == 5 and d['batches'] == 3 for d in meal['dishes'])


@pytest.mark.asyncio
async def test_unapproved_batch_never_calls_provider(monkeypatch):
    from scripts import verify_changes
    monkeypatch.setattr(verify_changes, 'select_photo', lambda _: ({'id': 'fixture', 'sha256': 'hash'}, b'fixture'))
    async def forbidden(*args, **kwargs):
        raise AssertionError('Unapproved batch must not call provider or start a workflow')
    monkeypatch.setattr(verify_changes, 'identify', forbidden)
    monkeypatch.setattr(verify_changes, 'workflow', forbidden)
    report = await verify_changes.run_batch()
    assert report['status'] == 'dry_run' and report['attempted_requests'] == 0
