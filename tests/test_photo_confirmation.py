"""No network: identity contradictions, confirmation boundaries and legacy receipts."""
import json
from pathlib import Path

import httpx
import pytest

from kitchen import vision
from kitchen.domain import Inventory, Preferences
from kitchen.proposals import ProposalConfirmation
from kitchen.store import Store
from test_vision import picture


@pytest.mark.parametrize('note,status',[
    ('难以确认是哪种绿叶菜', 'clear'),
    ('种类不确定，可能是小白菜', 'clear'),
    ('uncertain type of vegetable', 'clear'),
    ('外观相似', 'uncertain'),
])
@pytest.mark.asyncio
async def test_uncertain_identity_clears_preselection_and_quantity(monkeypatch,note,status):
    original=httpx.AsyncClient
    def provider(request):
        item={'name':'绿叶菜','ingredient_id':'bok_choy','identity_status':status,'note':note,
              'package_quantity':200,'package_unit':'g','label_text':'净含量200g','sealed':True}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'items':[item]})}}]})
    monkeypatch.setattr(vision.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(provider),**kw))
    monkeypatch.setenv('DEEPSEEK_API_KEY','unit-test-only')
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE','1')
    result=await vision.identify(picture(),True)
    item=result['items'][0]
    assert result['source']=='vision'
    assert item['ingredient_id'] is None and item['suggested_quantity'] is None
    assert item['suggested_ingredient_id']=='bok_choy' and item['identity_requires_review']


def test_quantity_uncertainty_does_not_change_known_identity():
    item=vision.Observation(name='牛奶',ingredient_id='milk',note='剩余数量不确定',identity_status='clear')
    assert vision.identity_review(item)[0]=='clear'


@pytest.mark.parametrize('kind',['stocktake','add'])
def test_photo_confirmation_requires_identity_and_is_idempotent(tmp_path,kind):
    store=Store(tmp_path/'photo.db');user,_=store.new_user()
    stock=store.save_inventory(user,Inventory(items=[{'ingredient_id':'egg','quantity':3,'unit':'piece'}]))
    proposal=store.create_proposal(user,kind,{'source':'vision','items':[]},stock.version,Preferences())
    body={'inventory_version':stock.version,'changes':[{'ingredient_id':'egg','action':'set' if kind=='stocktake' else 'add','quantity':2,'unit':'piece'}]}
    with pytest.raises(ValueError,match='逐项核对'):
        store.confirm_proposal(user,proposal['id'],ProposalConfirmation.model_validate(body))
    assert store.inventory(user)==stock
    body['changes'][0]['identity_confirmed']=True
    confirmed=ProposalConfirmation.model_validate(body)
    first=store.confirm_proposal(user,proposal['id'],confirmed)
    second=store.confirm_proposal(user,proposal['id'],confirmed)
    assert second['already_confirmed']
    assert store.inventory(user).items[0].quantity==(2 if kind=='stocktake' else 5)
    assert store.inventory(user).version==first['inventory']['version']


def test_keep_unknown_photo_and_legacy_receipt(tmp_path):
    store=Store(tmp_path/'photo.db');user,_=store.new_user()
    stock=store.inventory(user)
    proposal=store.create_proposal(user,'stocktake',{'image_count':1,'items':[]},stock.version,Preferences())
    body=ProposalConfirmation(inventory_version=stock.version,changes=[{'ingredient_id':'egg','action':'keep','unit':'piece'}])
    first=store.confirm_proposal(user,proposal['id'],body)
    assert first['inventory']==stock.model_dump(mode='json')
    # Old saved fingerprint omitted the newly added field. Existing receipts still replay.
    old=body.model_dump(mode='json');old['changes'][0].pop('identity_confirmed')
    with store.db() as db:
        db.execute('UPDATE proposals SET fingerprint=? WHERE id=?',(json.dumps(old),proposal['id']))
    assert store.confirm_proposal(user,proposal['id'],body)['already_confirmed']


@pytest.mark.asyncio
async def test_real_closed_egg_carton_error_is_blocked_on_replay(monkeypatch):
    fixture=json.loads((Path(__file__).parent/'fixtures/vision-identity-veg-fridge.json').read_text(encoding='utf-8'))
    original=httpx.AsyncClient
    monkeypatch.setattr(vision.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(lambda request:httpx.Response(200,json=fixture)),**kw))
    monkeypatch.setenv('DEEPSEEK_API_KEY','unit-test-only')
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE','1')
    result=await vision.identify(picture(),True)
    egg=next(x for x in result['items'] if x['suggested_ingredient_id']=='egg')
    assert egg['ingredient_id'] is None and egg['identity_status']=='uncertain'
    assert egg['visible_count'] is None and egg['suggested_quantity'] is None
    assert all(x['suggested_quantity'] is None for x in result['items'])


@pytest.mark.asyncio
async def test_even_clear_piece_count_needs_explicit_quantity_entry(monkeypatch):
    original=httpx.AsyncClient
    fixture={'items':[{'name':'鸡蛋','ingredient_id':'egg','identity_status':'clear','visible_count':3,'obscured':False}]}
    monkeypatch.setattr(vision.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(fixture)}}]})),**kw))
    monkeypatch.setenv('DEEPSEEK_API_KEY','unit-test-only')
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE','1')
    item=(await vision.identify(picture(),True))['items'][0]
    assert item['visible_count']==3 and item['ingredient_id']=='egg'
    assert item['suggested_quantity'] is None
