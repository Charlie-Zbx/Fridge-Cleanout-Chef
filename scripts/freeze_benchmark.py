"""Freeze 20 contexts for a later explicitly authorized benchmark. No model calls."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_offline import build_context, SCENARIOS


def cases():
    selected=list(SCENARIOS[:16])
    for n in (3,4,5):
        selected.append((str(14+n).zfill(2),f'{n}人两顿与分批制作',{'diners':n,'stock':{'egg':20,'cabbage':1500,'tofu':1500},'minutes_per_meal':90},'ready'))
    selected.append(('20','五人份分批时间超过限制',{'diners':5,'stock':{'egg':20,'cabbage':1500,'tofu':1500},'minutes_per_meal':20},'no_plan'))
    return [{'id':ident,'title':title,'expected':expected,'message':title+'。请按已确认条件安排饭菜。','context':build_context(**changes).model_dump(mode='json')} for ident,title,changes,expected in selected]


if __name__=='__main__':
    destination=ROOT/'artifacts'/'benchmark-v2-contexts.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps({'notice':'冻结开发场景，配方仍为待审核示例；尚未运行真实模型对照。','cases':cases()},ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Frozen 20 cases: {destination}; real API calls: 0; three-arm budget <=260 requests.')
