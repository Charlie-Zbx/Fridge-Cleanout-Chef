"""Two Agent checks + four new-photo batches. No request without new batch approval."""
import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import httpx
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kitchen.agent import run_agent
from kitchen.catalog import recipes
from kitchen.domain import Context, Plan
from kitchen.planning import evaluate
from kitchen.settings import require_live
from kitchen.vision import identify
from scripts.verify_changes import BatchBudget, VerificationFailure, write
from scripts.vision_smoke import select_photo


async def run_batch(approved=None, remaining_photos=False):
    spec = json.loads((ROOT / 'evaluation/efficiency-batch.json').read_text(encoding='utf-8'))
    if remaining_photos:
        names = {'egg_container', 'overlapping_views'}
        spec = {**spec, 'batch_id':'remaining-photos-after-format-fix-v1', 'agent_cases':[],
                'photo_cases':[x for x in spec['photo_cases'] if x['id'] in names],
                'limits':{name:1 for name in ('egg_container','overlapping_views')}, 'max_requests':2}
    photos = {ident: select_photo(ident) for case in spec['photo_cases'] for ident in case['images']}
    if approved != spec['max_requests']:
        return {'status': 'dry_run', 'max_requests': spec['max_requests'], 'limits': spec['limits'],
                'photo_cases': spec['photo_cases'], 'attempted_requests': 0}
    require_live(True)
    output = ROOT / 'artifacts' / ('efficiency-live-' + str(time.time_ns()))
    output.mkdir(parents=True)
    write(output / 'specification.json', spec)
    write(output / 'code-versions.json', {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in ['kitchen/agent.py','kitchen/planning.py','kitchen/vision.py','kitchen/data/recipes.json']})
    budget = BatchBudget(output, spec['limits'])
    old_dir = os.environ.get('KITCHEN_DATA_DIR')
    os.environ['KITCHEN_DATA_DIR'] = str(output / 'runtime')
    report = {'directory': str(output), 'agents': [], 'photos': [], 'inventory_updates': 0}
    try:
        async with asyncio.timeout(420):
            for case in spec['agent_cases']:
                budget.enter(case['id'])
                ctx = Context.model_validate({'inventory':case['inventory'], 'preferences':case['preferences'], 'recipes':recipes()})
                frozen = ctx.model_dump_json()
                result = await run_agent(ctx, case['message'], 'efficiency-'+case['id'], mode='live', consent=True,
                                         previous=case['previous'], checkpoint_path=output/(case['id']+'-checkpoints.db'), before_model=budget.charge)
                write(output/(case['id']+'.json'), result)
                if ctx.model_dump_json() != frozen or result['status'] != case['expected_status']:
                    raise VerificationFailure('Unexpected state or status for '+case['id'])
                if case['expected_status'] == 'ready':
                    if not evaluate(Plan.model_validate(result['plan']),ctx)['feasible'] or not result.get('validation',{}).get('feasible'):
                        raise VerificationFailure('Feasible control failed independent validation')
                elif result.get('termination') != 'verified_no_single_dish' or result.get('plan') is not None:
                    raise VerificationFailure('No-plan case lacks a verified full-library proof')
                calls = [e for e in result['trace'] if e['kind']=='mcp_tool']
                report['agents'].append({'id':case['id'],'status':result['status'],'model_calls':result['model_calls'],
                                         'mcp_calls':len(calls),'search_calls':sum(e['tool'].endswith('search_recipes') for e in calls),
                                         'cache_hits':sum(e['kind']=='tool_cache' for e in result['trace']),
                                         'usage':result.get('usage',{}),'duration_ms':result.get('duration_ms')})
            for case in spec['photo_cases']:
                budget.enter(case['id'])
                write(output/(case['id']+'-input.json'), [{'id':ident,'sha256':photos[ident][0]['sha256'],'source':photos[ident][0]['source']} for ident in case['images']])
                async with asyncio.timeout(40):
                    result = await identify([photos[ident][1] for ident in case['images']], True, before_model=budget.charge,
                                            on_response=lambda data: write(output/(case['id']+'-provider.json'), data))
                write(output/(case['id']+'-observations.json'), result)
                if not result['requires_confirmation']:
                    raise VerificationFailure('Photo did not require confirmation')
                report['photos'].append({'id':case['id'],'images':case['images'],'observations':len(result['items']),'usage':result.get('usage',{}),'quality_review':'pending'})
            report['status'] = 'completed'
    except Exception as error:
        report.update(status='failed',stage=budget.stage,error_type=type(error).__name__)
        if isinstance(error, VerificationFailure):
            report['reason'] = str(error)
        if isinstance(error, ValidationError):
            report['validation_errors'] = [{'location':list(e['loc']),'type':e['type']} for e in error.errors()]
        if isinstance(error, httpx.HTTPStatusError):
            report['http_status'] = error.response.status_code
        captured = output / (str(budget.stage)+'-provider.json')
        if captured.exists():
            report['failed_response_usage'] = json.loads(captured.read_text(encoding='utf-8')).get('usage',{})
    finally:
        if old_dir is None:
            os.environ.pop('KITCHEN_DATA_DIR',None)
        else:
            os.environ['KITCHEN_DATA_DIR'] = old_dir
    report.update(attempted_requests=sum(budget.counts.values()),stage_attempts=budget.counts,authorization_closed=True,
                  unused_requests_not_carried_forward=spec['max_requests']-sum(budget.counts.values()))
    write(output/'report.json',report)
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--approve-max-calls',type=int,choices=[2,16])
    parser.add_argument('--remaining-photos',action='store_true',help='Separate approval: only egg-container and overlapping views, max 2 requests')
    args=parser.parse_args()
    result=asyncio.run(run_batch(args.approve_max_calls,args.remaining_photos))
    print(json.dumps(result,ensure_ascii=False,indent=2))
    sys.exit(1 if result['status']=='failed' else 0)
