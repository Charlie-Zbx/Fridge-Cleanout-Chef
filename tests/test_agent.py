import pytest
from kitchen.agent import run_agent, parse_answer


@pytest.mark.asyncio
async def test_real_stdio_mcp_and_langchain_repair(context,tmp_path):
    result=await run_agent(context,"安排两顿饭，先用卷心菜。","integration-run",checkpoint_path=tmp_path/"checkpoints.db")
    assert result["status"]=="ready",result
    assert result["mode"]=="offline" and result["usage"]["input_tokens"]==0
    assert result["model_calls"]<=6
    discovery=next(t for t in result["trace"] if t["kind"]=="mcp_discovery")
    assert len(discovery["tools"])==3
    checks=[t for t in result["trace"] if t["kind"]=="mcp_tool" and t["tool"].endswith("evaluate_plan")]
    assert len(checks)==2
    assert not checks[0]["result"]["feasible"] and checks[1]["result"]["feasible"]
    assert result["validation"]["feasible"]


@pytest.mark.asyncio
async def test_live_denied_before_model_call(context,tmp_path):
    with pytest.raises(PermissionError):
        await run_agent(context,"test","blocked",mode="live",consent=True,checkpoint_path=tmp_path/"c.db")


@pytest.mark.asyncio
async def test_no_stock_asks_without_calls(context,tmp_path):
    context.inventory.items=[]
    result=await run_agent(context,"半盒豆腐","empty",checkpoint_path=tmp_path/"c.db")
    assert result["status"]=="needs_input" and result["model_calls"]==0


@pytest.mark.asyncio
async def test_no_reviewed_recipes_refuses(context,tmp_path):
    context.preferences.allow_draft_recipes=False
    result=await run_agent(context,"安排两顿饭","no-review",checkpoint_path=tmp_path/"c.db")
    assert result["status"]=="no_plan",result


def test_invalid_final_plan_schema():
    with pytest.raises(ValueError):parse_answer('{"status":"ready","message":"done","plan":null}')


@pytest.mark.asyncio
async def test_no_replanning_baseline_stops_after_first_check(context,tmp_path):
    result=await run_agent(context,"两顿饭","check-only",allow_replanning=False,checkpoint_path=tmp_path/'c.db')
    assert result['status']=='no_plan',result
    assert result['model_calls']==3
    assert not result['validation']['feasible']


@pytest.mark.asyncio
async def test_model_round_budget():
    from kitchen.agent import Budget,RunLimit
    from types import SimpleNamespace
    budget=Budget([])
    async def handler(request):return SimpleNamespace(result=[])
    for _ in range(6):await budget.awrap_model_call(None,handler)
    with pytest.raises(RunLimit):await budget.awrap_model_call(None,handler)
    assert budget.calls==6
