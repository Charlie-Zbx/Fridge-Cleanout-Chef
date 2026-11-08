"""Twenty deterministic scenarios. This is integration evidence, NOT an LLM benchmark."""
import asyncio
import argparse
import csv
import json
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['KITCHEN_ENABLE_LIVE']='0'
os.environ['LANGSMITH_TRACING']='false'
os.environ['LANGCHAIN_TRACING_V2']='false'
from kitchen.catalog import recipes,ingredients
from kitchen.domain import Context,Inventory,Preferences,Plan
from kitchen.agent import run_agent
from kitchen.planning import search,evaluate


def build_context(stock=None,**changes):
    values=stock if stock is not None else {'egg':3,'cabbage':200,'tofu':300}
    pantry=changes.pop('pantry',['oil','salt'])
    prefs=Preferences(priority_ingredients=['cabbage'],allow_draft_recipes=True)
    for key,value in changes.items():setattr(prefs,key,value)
    return Context(inventory=Inventory(items=[{'ingredient_id':key,'quantity':value,'unit':ingredients()[key].unit} for key,value in values.items()],pantry=pantry),preferences=prefs,recipes=recipes())


SCENARIOS=[
 ('01','跨餐冲突后可修复',{},'ready'),
 ('02','刚好足够两种菜',{'stock':{'egg':2,'cabbage':100,'tofu':150}},'ready'),
 ('03','食材不足两顿',{'stock':{'egg':1,'cabbage':100}},'no_plan'),
 ('04','未确认调料',{'pantry':[]},'no_plan'),
 ('05','厨具不匹配',{'equipment':['pot']},'no_plan'),
 ('06','时间仅十分钟',{'minutes_per_meal':10},'no_plan'),
 ('07','两人份库存不足',{'diners':2},'no_plan'),
 ('08','两人份库存足够',{'diners':2,'stock':{'egg':4,'cabbage':400,'tofu':600}},'ready'),
 ('09','排除鸡蛋',{'excluded_allergens':['egg']},'ready'),
 ('10','排除大豆仍有解',{'excluded_allergens':['soy'],'stock':{'egg':4,'cabbage':300}},'ready'),
 ('11','排除豆腐后不足',{'excluded_ingredients':['tofu']},'no_plan'),
 ('12','未审核菜谱不获准使用',{'allow_draft_recipes':False},'no_plan'),
 ('13','只安排一顿',{'meals':1},'ready'),
 ('14','空库存',{'stock':{}},'needs_input'),
 ('15','库存均为零',{'stock':{'egg':0,'tofu':0}},'needs_input'),
 ('16','汤锅与蔬菜豆腐汤',{'stock':{'bok_choy':300,'tofu':300},'pantry':['salt'],'equipment':['pot']},'ready'),
 ('17','同一道菜两顿恰好足量',{'stock':{'tofu':300}},'ready'),
 ('18','缩短时间后没有组合',{'minutes_per_meal':15},'no_plan'),
 ('19','酱油中的小麦限制',{'stock':{'pepper':240,'pork':200},'pantry':['oil','soy_sauce'],'minutes_per_meal':30,'excluded_allergens':['wheat']},'no_plan'),
 ('20','生大米不能视作熟饭',{'stock':{'rice':200,'egg':2}},'no_plan'),
]


async def main(suite=None):
    output=ROOT/'artifacts'
    output.mkdir(exist_ok=True)
    records=[]
    cases=json.loads(Path(suite).read_text(encoding='utf-8'))['cases'] if suite else [{'id':i,'title':t,'expected':e,'context':build_context(**c).model_dump(mode='json')} for i,t,c,e in SCENARIOS]
    for case in cases:
        id,title,expected=case['id'],case['title'],case['expected']
        ctx=Context.model_validate(case['context'])
        available=[r for r in search(ctx,limit=30)['candidates'] if r['available_now']]
        naive=None
        if available:
            draft=Plan(meals=[{'dishes':[{'recipe_id':available[0]['recipe_id'],'servings':ctx.preferences.diners}]} for _ in range(ctx.preferences.meals)])
            naive=evaluate(draft,ctx)['feasible']
        result=await run_agent(ctx,title,'offline-eval-'+id,checkpoint_path=output/'offline-eval-checkpoints.db')
        record={'scenario':id,'title':title,'expected':expected,'actual':result['status'],'pass':result['status']==expected,'mode':'offline-scripted-not-llm','initial_rule_feasible':naive,'final_feasible':result.get('validation',{}).get('feasible',False),'model_rounds':result['model_calls'],'mcp_calls':sum(t['kind']=='mcp_tool' for t in result['trace']),'duration_ms':result.get('duration_ms',0),'real_api_calls':0,'trace':result['trace']}
        records.append(record)
        print(f"{id} {'PASS' if record['pass'] else 'FAIL'} {title}: {result['status']}",flush=True)
    summary={'notice':'离线规则与真实 LangChain/MCP 集成测试，未调用 DeepSeek，不代表模型效果。','count':len(records),'passed':sum(r['pass'] for r in records),'real_api_calls':0,'cases':records}
    (output/('offline-evaluation-v2.json' if suite else 'offline-evaluation.json')).write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    fields=[k for k in records[0] if k!='trace']
    with (output/('offline-evaluation-v2.csv' if suite else 'offline-evaluation.csv')).open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows({k:v for k,v in r.items() if k!='trace'} for r in records)
    print(f"{summary['passed']}/{summary['count']} passed; real API calls: 0",flush=True)
    if summary['passed']!=summary['count']:sys.exit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--suite')
    asyncio.run(main(parser.parse_args().suite))
