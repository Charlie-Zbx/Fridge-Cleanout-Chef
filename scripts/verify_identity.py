"""Two public-photo identity checks. Requires a fresh, exact two-request approval."""
import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kitchen.settings import require_live
from kitchen.vision import identify
from scripts.verify_changes import BatchBudget, write
from scripts.vision_smoke import select_photo


async def run(approved=None):
    spec={'photos':['veg_bin','veg_fridge'],'max_requests':2,'max_output_tokens':3000,
          'per_request_seconds':40,'batch_seconds':100,'retries':0,'inventory_updates':0}
    if approved!=2: return {**spec,'status':'dry_run','attempted_requests':0}
    require_live(True)
    photos={name:select_photo(name) for name in spec['photos']}
    output=ROOT/'artifacts'/('identity-live-'+str(time.time_ns()));output.mkdir(parents=True)
    write(output/'specification.json',{**spec,'vision_sha256':hashlib.sha256((ROOT/'kitchen/vision.py').read_bytes()).hexdigest(),
          'inputs':[{key:row[key] for key in ('id','path','sha256','source')} for row,_ in photos.values()]})
    budget=BatchBudget(output,{name:1 for name in spec['photos']})
    report={**spec,'directory':str(output),'photos':[]}
    try:
        async with asyncio.timeout(100):
            for name,(_,raw) in photos.items():
                budget.enter(name)
                async with asyncio.timeout(40):
                    result=await identify(raw,True,before_model=budget.charge,on_response=lambda response:write(output/(name+'-provider.json'),response))
                write(output/(name+'-observations.json'),result)
                report['photos'].append({'id':name,'usage':result.get('usage',{}),'observations':len(result['items']),
                    'cleared_identity':sum(x['ingredient_id'] is None for x in result['items']),
                    'suggested_quantities':sum(x['suggested_quantity'] is not None for x in result['items']),
                    'identity_statuses':[x['identity_status'] for x in result['items']],
                    'all_require_identity_review':all(x['identity_requires_review'] for x in result['items']),
                    'quality_review':'pending'})
            report['status']='completed'
    except Exception as error:
        report.update(status='failed',stage=budget.stage,error_type=type(error).__name__)
        captured=output/(str(budget.stage)+'-provider.json')
        if captured.exists(): report['failed_response_usage']=json.loads(captured.read_text(encoding='utf-8')).get('usage',{})
    report.update(attempted_requests=sum(budget.counts.values()),stage_attempts=budget.counts,
                  authorization_closed=True,unused_requests_not_carried_forward=2-sum(budget.counts.values()))
    write(output/'report.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approve-max-calls',type=int,choices=[2])
    args=parser.parse_args()
    result=asyncio.run(run(args.approve_max_calls))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    sys.exit(1 if result['status']=='failed' else 0)
