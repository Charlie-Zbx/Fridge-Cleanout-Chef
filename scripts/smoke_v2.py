"""One intake + one five-person Agent task. Dry run unless explicitly approved."""
import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kitchen.agent import run_agent
from kitchen.catalog import recipes
from kitchen.domain import Context,Inventory,Preferences
from kitchen.proposals import interpret
from kitchen.settings import require_live


async def main(approved):
    if approved!=7:
        print('DRY RUN. No requests. This test needs explicit approval for <=7 text model requests: intake <=1, planning <=6. No images, no retries, <=3000 output tokens/request.')
        return
    require_live(True)
    output=ROOT/'artifacts'/('v2-live-smoke-'+str(time.time_ns()))
    output.mkdir(parents=True)
    attempts=0
    def charge():
        nonlocal attempts
        if attempts>=7: raise PermissionError('Authorized request budget exhausted')
        attempts+=1
        (output/'budget.json').write_text(json.dumps({'approved':7,'attempted':attempts}),encoding='utf-8')
    inventory=Inventory(items=[{'ingredient_id':'egg','quantity':20,'unit':'piece'},{'ingredient_id':'cabbage','quantity':1500,'unit':'g'},{'ingredient_id':'tofu','quantity':1500,'unit':'g'}],pantry=['oil','salt'])
    prefs=Preferences(priority_ingredients=['cabbage'],allow_draft_recipes=True)
    async with asyncio.timeout(40):
        intake=await interpret('改成五个人吃，安排两顿，每顿最多90分钟，其他条件保持不变。',prefs,inventory,mode='live',consent=True,before_model=charge)
    (output/'intake.json').write_text(json.dumps(intake,ensure_ascii=False,indent=2),encoding='utf-8')
    expected=prefs.model_copy(update={'diners':5,'minutes_per_meal':90})
    actual=Preferences.model_validate(intake['preferences'])
    if actual!=expected or intake.get('items') or intake.get('questions'):
        print('Intake did not match the frozen test expectation; stopped before planning. Saved:',output)
        return
    # Confirmation is the test fixture, not an autonomous edit of a user's kitchen.
    context=Context(inventory=inventory,preferences=actual,recipes=recipes())
    (output/'context.json').write_text(context.model_dump_json(indent=2),encoding='utf-8')
    result=await run_agent(context,'按已确认的五人、两顿、每顿90分钟、平底锅条件规划；优先消耗卷心菜。','v2-authorized-smoke',mode='live',consent=True,checkpoint_path=output/'checkpoints.db',before_model=charge)
    (output/'agent.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'directory':str(output),'attempted_requests':attempts,'intake_usage':intake.get('usage'),'status':result['status'],'message':result['message'],'plan':result.get('plan'),'planning_usage':result.get('usage'),'duration_ms':result.get('duration_ms'),'feasible':result.get('validation',{}).get('feasible')},ensure_ascii=False))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approve-max-calls',type=int)
    asyncio.run(main(parser.parse_args().approve_max_calls))
