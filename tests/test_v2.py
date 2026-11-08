import asyncio
import json
from decimal import Decimal
import httpx
import pytest
from fastapi.testclient import TestClient
from kitchen.catalog import recipes
from kitchen.domain import Preferences, Dish, Plan, Inventory
from kitchen.planning import evaluate, search
from kitchen.portions import portion
from kitchen.proposals import ProposalConfirmation, offline_intake, interpret
from kitchen.store import Store, Conflict, now
from kitchen.api import create_app
from test_vision import picture

HEADERS={'X-Kitchen-Client':'fridge-web'}


@pytest.mark.parametrize('n',[1,2,3,4,5])
def test_scaled_people_time_and_inventory(context,n):
    context.preferences.diners=n
    context.preferences.meals=1
    context.preferences.minutes_per_meal=120
    context.inventory.items[2].quantity=Decimal(1000)
    recipe=next(r for r in context.recipes if r.id=='pan_tofu')
    report=evaluate(Plan(meals=[{'dishes':[{'recipe_id':recipe.id,'servings':n}]}]),context)
    assert report['feasible']
    assert report['consumption']['tofu']==150*n
    assert report['meals'][0]['minutes']==recipe.serving_profiles[str(n)].minutes
    assert report['meals'][0]['dishes'][0]['batches']==(n+1)//2


@pytest.mark.parametrize('n',[0,6,-1,1.5,True,'3'])
def test_invalid_people(n):
    with pytest.raises(ValueError): Preferences(diners=n)
    with pytest.raises(ValueError): Dish(recipe_id='pan_tofu',servings=n)


def test_base_portions_round_count_up_and_missing_profile():
    recipe=next(r for r in recipes() if r.id=='cabbage_egg')
    recipe.base_servings=3
    assert portion(recipe,2)['quantities'][1]['quantity']==2
    recipe.serving_profiles={}
    with pytest.raises(ValueError):portion(recipe,5)


def test_five_people_time_rejects_and_three_dishes_aggregate(context):
    context.preferences.diners=5
    context.preferences.meals=1
    context.inventory.items[2].quantity=Decimal(1000)
    report=evaluate(Plan(meals=[{'dishes':[{'recipe_id':'pan_tofu','servings':5}]}]),context)
    assert any(v['code']=='time' for v in report['violations'])
    context.preferences.diners=1
    context.preferences.minutes_per_meal=120
    plan=Plan(meals=[{'dishes':[{'recipe_id':x,'servings':1} for x in ['cabbage_egg','stir_cabbage','pan_tofu']]}])
    assert any(v['code']=='stock' for v in evaluate(plan,context)['violations'])


def setup_store(tmp_path,context):
    store=Store(tmp_path/'db.sqlite')
    user,_=store.new_user()
    stock=store.save_inventory(user,context.inventory)
    proposal=store.create_proposal(user,'stocktake',{'items':[]},stock.version,store.preferences(user))
    return store,user,proposal


def test_stocktake_sets_preserves_unseen_and_exact_retry(tmp_path,context):
    store,user,proposal=setup_store(tmp_path,context)
    body=ProposalConfirmation(inventory_version=proposal['inventory_version'],changes=[{'ingredient_id':'egg','unit':'piece','quantity':2,'action':'set'}])
    result=store.confirm_proposal(user,proposal['id'],body)
    assert {x['ingredient_id']:Decimal(x['quantity']) for x in result['inventory']['items']}=={'egg':2,'cabbage':200,'tofu':300}
    assert store.confirm_proposal(user,proposal['id'],body)['already_confirmed']
    body.changes[0].quantity=Decimal(1)
    with pytest.raises(Conflict):store.confirm_proposal(user,proposal['id'],body)
    other,_=store.new_user()
    with pytest.raises(KeyError):store.confirm_proposal(other,proposal['id'],body)


def test_add_new_quantity_and_preserve(tmp_path,context):
    store,user,p=setup_store(tmp_path,context)
    b=ProposalConfirmation(inventory_version=p['inventory_version'],changes=[{'ingredient_id':'egg','unit':'piece','quantity':2,'action':'add'},{'ingredient_id':'tofu','unit':'g','action':'keep'}])
    store.confirm_proposal(user,p['id'],b)
    assert store.inventory(user).items[0].quantity==5


@pytest.mark.parametrize('case',['stale','expired'])
def test_stale_and_expired_observations(tmp_path,context,case):
    store,user,p=setup_store(tmp_path,context)
    if case=='stale':store.save_inventory(user,store.inventory(user))
    else:
        with store.db() as db:db.execute("UPDATE proposals SET expires_at='2000-01-01' WHERE id=?",(p['id'],))
    with pytest.raises(Conflict):store.confirm_proposal(user,p['id'],ProposalConfirmation(inventory_version=p['inventory_version']))


def test_duplicate_observations_require_merge():
    item={'ingredient_id':'egg','quantity':2,'unit':'piece'}
    with pytest.raises(ValueError):ProposalConfirmation(inventory_version=0,changes=[item,item])


def test_intake_confirm_preserves_constraints(tmp_path,context):
    store,user,p=setup_store(tmp_path,context)
    prefs=Preferences(excluded_allergens=['egg'])
    store.save_preferences(user,prefs)
    result=offline_intake('改成五个人吃，每顿45分钟',prefs)
    assert result['preferences']['diners']==5
    assert result['preferences']['excluded_allergens']==['egg']
    proposal=store.create_proposal(user,'intake',result,store.inventory(user).version,prefs)
    assert store.preferences(user).diners==1
    store.confirm_proposal(user,proposal['id'],ProposalConfirmation(inventory_version=proposal['inventory_version'],preferences=Preferences.model_validate(result['preferences'])))
    assert store.preferences(user).diners==5
    result=offline_intake('半颗卷心菜，一盒豆腐',prefs)
    assert result['questions'] and all(x['quantity'] is None for x in result['items'])


def test_stocktake_invalidates_existing_plan(tmp_path,context):
    store,user,p=setup_store(tmp_path,context)
    store.save_run(user,{'id':'old','revision':1,'created_at':now(),'status':'ready','plan':{'meals':[]}})
    store.confirm_proposal(user,p['id'],ProposalConfirmation(inventory_version=p['inventory_version'],changes=[{'ingredient_id':'egg','quantity':1,'unit':'piece'}]))
    assert store.run(user,'old')['status']=='needs_input'


def test_actual_extra_consumption_invalidates_remaining_meal(tmp_path,context):
    store,user,p=setup_store(tmp_path,context)
    prefs=Preferences(allow_draft_recipes=True)
    store.save_run(user,{'id':'old','revision':1,'created_at':now(),'status':'ready','preferences':prefs.model_dump(),'plan':{'meals':[{'dishes':[{'recipe_id':'pan_tofu','servings':1}]}]*2}})
    store.confirm(user,'old',0,1,p['inventory_version'],{'tofu':200})
    assert store.run(user,'old')['status']=='needs_input'


def test_persistent_global_and_personal_quota(tmp_path,monkeypatch):
    store=Store(tmp_path/'q.db');user,_=store.new_user()
    monkeypatch.setenv('KITCHEN_DAILY_USER_CALLS','1')
    store.record_model_attempt(user,'vision')
    with pytest.raises(PermissionError):Store(store.path).record_model_attempt(user,'planning')
    other,_=store.new_user();monkeypatch.setenv('KITCHEN_DAILY_GLOBAL_CALLS','1')
    with pytest.raises(PermissionError):store.record_model_attempt(other,'intake')


def test_interrupted_running_tasks_no_restart(tmp_path):
    store=Store(tmp_path/'r.db');user,_=store.new_user()
    store.save_run(user,{'id':'run','revision':1,'created_at':now(),'status':'running'})
    store.recover_interrupted()
    assert store.run(user,'run')['error_type']=='Interrupted'


@pytest.mark.asyncio
async def test_multi_photo_evidence_and_duplicates(monkeypatch):
    from kitchen import vision
    original=httpx.AsyncClient;calls=[]
    def handler(request):
        body=json.loads(request.content);calls.append(body)
        assert len(body['messages'][0]['content'])==4
        values=[{'name':'豆腐','ingredient_id':'tofu','label_text':'净含量400g','package_quantity':400,'package_unit':'g','remaining_fraction':0.5,'image_indices':[1,2]}, {'name':'卷心菜','ingredient_id':'cabbage','package_quantity':500,'package_unit':'g','remaining_fraction':1}, {'name':'鸡蛋','ingredient_id':'egg','visible_count':4,'duplicate_group':'A','image_indices':[2,3]}]
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'items':values})}}]})
    monkeypatch.setattr(vision.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE','1');monkeypatch.setenv('DEEPSEEK_API_KEY','fake-test-key')
    result=await vision.identify([picture()]*3,True)
    assert len(calls)==1
    assert result['items'][0]['suggested_quantity']==200
    assert result['items'][1]['suggested_quantity'] is None
    assert result['items'][2]['suggested_quantity'] is None
    with pytest.raises(ValueError):await vision.identify([picture()]*4,True)
    assert len(calls)==1


@pytest.mark.asyncio
async def test_true_langchain_intake_with_mock_provider(monkeypatch,context):
    from kitchen import agent
    from langchain_deepseek import ChatDeepSeek
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,json={'id':'test','object':'chat.completion','created':1,'model':'deepseek-flash','choices':[{'index':0,'message':{'role':'assistant','content':json.dumps({'preferences_patch':{'diners':5},'questions':[],'items':[]})},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':20,'total_tokens':30}})
    client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(agent,'live_model',lambda:ChatDeepSeek(model='deepseek-flash',api_key='fake-test-key',http_async_client=client,max_retries=0))
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE','1');monkeypatch.setenv('DEEPSEEK_API_KEY','fake-test-key')
    try: result=await interpret('五个人吃',context.preferences,context.inventory,mode='live',consent=True)
    finally: await client.aclose()
    assert len(requests)==1 and result['preferences']['diners']==5


def test_async_job_idempotency_progress_and_isolation(tmp_path,monkeypatch):
    from kitchen import agent
    calls=[]
    async def fake(context,message,run_id,**kw):
        calls.append(run_id)
        kw['on_progress']([{'kind':'mcp_discovery','tools':['one']}])
        await asyncio.Event().wait()  # held until lifespan cancellation; no timing race
        return {'status':'no_plan','message':'test no plan','plan':None,'trace':[],'model_calls':0,'mode':'offline','usage':{}}
    monkeypatch.setattr(agent,'run_agent',fake)
    with TestClient(create_app(tmp_path/'api.db')) as client:
        prefs=client.post('/api/session',headers=HEADERS).json()['preferences']
        body={'preferences':prefs,'request_id':'same-id-test'}
        first=client.post('/api/runs',headers=HEADERS,json=body)
        assert first.status_code==202
        ident=first.json()['id']
        second=client.post('/api/runs',headers=HEADERS,json=body)
        assert second.json()['id']==ident and len(calls)==1
        assert client.get('/api/runs/'+ident).json()['status']=='running'
        changed={**body,'message':'different'}
        assert client.post('/api/runs',headers=HEADERS,json=changed).status_code==409
        assert client.get('/api/runs/'+ident).json()['trace'][0]['kind']=='mcp_discovery'


def test_invite_code_and_attempt_limit(tmp_path,monkeypatch):
    monkeypatch.setenv('KITCHEN_ACCESS_CODE','test-invite')
    with TestClient(create_app(tmp_path/'api.db')) as client:
        assert client.post('/api/session',headers=HEADERS).status_code==401
        assert client.post('/api/session',headers=HEADERS,json={'access_code':'test-invite'}).status_code==200
        assert client.get('/api/inventory').status_code==200


def test_search_pagination(context):
    all_rows=search(context,limit=30)
    first=search(context,limit=1)
    second=search(context,limit=1,offset=1)
    assert first['total']==all_rows['total']
    assert first['candidates']+second['candidates']==all_rows['candidates'][:2]


def test_backup_restore_preserves_data(tmp_path,context):
    from scripts.backup import transfer
    store=Store(tmp_path/'source'/'kitchen.db');user,token=store.new_user()
    store.save_inventory(user,context.inventory)
    transfer(store.path.parent,tmp_path/'backup')
    transfer(tmp_path/'backup',tmp_path/'restored')
    restored=Store(tmp_path/'restored'/'kitchen.db')
    assert restored.user_for_token(token)==user
    assert restored.inventory(user).items[0].quantity==3
    with pytest.raises(ValueError):transfer(tmp_path/'backup',tmp_path/'restored')


def test_label_must_agree_with_suggested_package_weight():
    from kitchen.vision import Observation,label_supports
    assert label_supports(Observation(name='豆腐',label_text='净含量0.4kg',package_quantity=400,package_unit='g'))
    assert not label_supports(Observation(name='豆腐',label_text='净含量200g',package_quantity=400,package_unit='g'))


def test_team_review_is_global_and_version_invalidates_personal(tmp_path,monkeypatch):
    from kitchen import store as module
    source=recipes();store=Store(tmp_path/'db');one,_=store.new_user();two,_=store.new_user()
    store.review(one,'pan_tofu',True)
    recipe=next(r for r in source if r.id=='pan_tofu');recipe.version+=1
    monkeypatch.setattr(module,'recipes',lambda:source)
    assert not next(r for r in store.recipes(one) if r.id=='pan_tofu').reviewed
    recipe.team_reviewed=True;recipe.team_reviewed_by='fixture-reviewer';recipe.team_reviewed_at='test-date'
    assert next(r for r in store.recipes(two) if r.id=='pan_tofu').reviewed


@pytest.mark.asyncio
async def test_final_answer_without_tool_evidence_is_rejected(context,tmp_path,monkeypatch):
    from kitchen import agent
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatResult,ChatGeneration
    good={'meals':[{'dishes':[{'recipe_id':'cabbage_egg','servings':1}]},{'dishes':[{'recipe_id':'pan_tofu','servings':1}]}]}
    class SkippingModel(agent.OfflineModel):
        def _generate(self,*args,**kwargs):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=json.dumps({'status':'ready','message':'claims success without tools','plan':good})))])
    monkeypatch.setattr(agent,'OfflineModel',SkippingModel)
    result=await agent.run_agent(context,'test','skip',checkpoint_path=tmp_path/'checks.db')
    assert result['status']=='no_plan'
    assert any(v['code']=='tool_evidence' for v in result['validation']['violations'])


def test_frozen_suite_covers_new_people():
    from scripts.freeze_benchmark import cases
    values=cases()
    assert len(values)==20
    assert {v['context']['preferences']['diners'] for v in values}=={1,2,3,4,5}


@pytest.mark.asyncio
async def test_real_mcp_error_cannot_be_success(context,tmp_path,monkeypatch):
    from kitchen import agent
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatResult,ChatGeneration
    class BrokenToolModel(agent.OfflineModel):
        def _generate(self,*args,**kwargs):
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content='',tool_calls=[self._call('get_recipe',{'recipe_id':'does_not_exist'})]))])
    monkeypatch.setattr(agent,'OfflineModel',BrokenToolModel)
    result=await agent.run_agent(context,'test','tool-error',checkpoint_path=tmp_path/'check.db')
    assert result['status']=='error'
    assert any(e['kind']=='mcp_tool' and not e.get('ok') for e in result['trace'])
