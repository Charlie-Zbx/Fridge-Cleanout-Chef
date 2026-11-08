"""Exercise the actual DeepSeek adapter using an in-memory HTTP transport.

No request leaves the process, and no real API key is used.
"""
import json
import httpx
import pytest
import langchain_deepseek
from kitchen.agent import run_agent


@pytest.mark.asyncio
async def test_deepseek_adapter_with_mock_http_and_real_mcp(context,tmp_path,monkeypatch):
    original=langchain_deepseek.ChatDeepSeek
    calls=[]
    bad={"meals":[{"dishes":[{"recipe_id":"cabbage_egg","servings":1}]},{"dishes":[{"recipe_id":"cabbage_egg","servings":1}]}]}
    good={"meals":[{"dishes":[{"recipe_id":"cabbage_egg","servings":1}]},{"dishes":[{"recipe_id":"pan_tofu","servings":1}]}]}
    def handler(request):
        assert request.url.host=='api.deepseek.com'
        body=json.loads(request.content)
        assert body['model']=='deepseek-flash'
        assert body['thinking']['type']=='disabled'
        calls.append(body)
        functions={x['function']['name'].split('_',1)[-1]:x['function']['name'] for x in body.get('tools',[])}
        def tool(suffix,args):
            name=next(x['function']['name'] for x in body['tools'] if x['function']['name'].endswith(suffix))
            return {'id':'mock_'+str(len(calls))+suffix,'type':'function','function':{'name':name,'arguments':json.dumps(args)}}
        message={'role':'assistant','content':None}
        if len(calls)==1:message['tool_calls']=[tool('search_recipes',{'limit':12})]
        elif len(calls)==2:message['tool_calls']=[tool('get_recipe',{'recipe_id':'cabbage_egg'}),tool('get_recipe',{'recipe_id':'pan_tofu'})]
        elif len(calls)==3:message['tool_calls']=[tool('evaluate_plan',{'plan':bad})]
        elif len(calls)==4:message['tool_calls']=[tool('evaluate_plan',{'plan':good})]
        else:message['content']=json.dumps({'status':'ready','message':'HTTP mock fixture, not a real model result.','plan':good})
        return httpx.Response(200,json={'id':'mock-completion','object':'chat.completion','created':0,'model':'deepseek-flash','choices':[{'index':0,'message':message,'finish_reason':'tool_calls' if 'tool_calls' in message else 'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':5,'total_tokens':15}})
    transport=httpx.MockTransport(handler)
    sync=httpx.Client(transport=transport)
    async_client=httpx.AsyncClient(transport=transport)
    def factory(**kwargs):
        return original(**kwargs,http_client=sync,http_async_client=async_client)
    monkeypatch.setattr(langchain_deepseek,'ChatDeepSeek',factory)
    monkeypatch.setenv('DEEPSEEK_API_KEY','unit-test-not-a-real-key')
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE','1')
    try:
        result=await run_agent(context,'根据已确认库存安排两顿','mock-contract',mode='live',consent=True,checkpoint_path=tmp_path/'checkpoints.db')
        assert result['status']=='ready',result
        assert len(calls)==5 and result['model_calls']==5
        assert result['validation']['feasible']
        assert result['usage']['input_tokens']==50
    finally:
        sync.close()
        await async_client.aclose()


def test_consent_is_required_even_with_key(monkeypatch):
    from kitchen.settings import require_live
    monkeypatch.setenv('DEEPSEEK_API_KEY','unit-test-not-a-real-key')
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE','1')
    with pytest.raises(PermissionError):require_live(False)
