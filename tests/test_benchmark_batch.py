import argparse
import json

import pytest

from scripts import benchmark_live


def test_case_subset_is_explicit_and_keeps_frozen_order():
    cases=[{'id':'01'},{'id':'02'},{'id':'03'}]
    assert benchmark_live.select_cases(cases,'03,01')==[cases[0],cases[2]]
    with pytest.raises(ValueError): benchmark_live.select_cases(cases,'01,01')
    with pytest.raises(ValueError): benchmark_live.select_cases(cases,'04')


@pytest.mark.asyncio
async def test_selected_benchmark_is_dry_until_exact_budget_approved(tmp_path,context,monkeypatch,capsys):
    path=tmp_path/'suite.json'
    path.write_text(json.dumps({'cases':[{'id':'01','context':context.model_dump(mode='json')},{'id':'02','context':context.model_dump(mode='json')}]}),encoding='utf-8')
    def denied(*args): raise AssertionError('live check should not be reached')
    monkeypatch.setattr(benchmark_live,'require_live',denied)
    args=argparse.Namespace(context=None,suite=str(path),case_ids='02',approve_max_calls=None,timeout_seconds=420,message='test')
    await benchmark_live.main(args)
    assert 'maximum 13 requests' in capsys.readouterr().out
    args.approve_max_calls=26
    with pytest.raises(SystemExit): await benchmark_live.main(args)


@pytest.mark.asyncio
async def test_identity_photo_batch_defaults_to_no_requests(monkeypatch):
    from scripts import verify_identity
    def denied(*args): raise AssertionError('No provider or upload without approval')
    monkeypatch.setattr(verify_identity,'require_live',denied)
    monkeypatch.setattr(verify_identity,'select_photo',denied)
    result=await verify_identity.run()
    assert result['status']=='dry_run' and result['attempted_requests']==0
