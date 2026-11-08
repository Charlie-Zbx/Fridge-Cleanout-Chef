import pytest
from scripts import verify_efficiency


@pytest.mark.asyncio
async def test_new_photo_batch_requires_explicit_new_approval(monkeypatch):
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE','1')
    monkeypatch.setenv('DEEPSEEK_API_KEY','fake-test-key')
    monkeypatch.setattr(verify_efficiency,'select_photo',lambda ident:({'id':ident,'sha256':'fixture'},b'fixture'))
    async def forbidden(*args,**kwargs):
        raise AssertionError('Unapproved batch cannot call a model')
    monkeypatch.setattr(verify_efficiency,'identify',forbidden)
    monkeypatch.setattr(verify_efficiency,'run_agent',forbidden)
    result=await verify_efficiency.run_batch()
    assert result['attempted_requests']==0 and result['status']=='dry_run'
    assert sum(result['limits'].values())==result['max_requests']==16
    pending=await verify_efficiency.run_batch(approved=16,remaining_photos=True)
    assert pending['status']=='dry_run' and pending['max_requests']==2
    assert [x['id'] for x in pending['photo_cases']]==['egg_container','overlapping_views']
