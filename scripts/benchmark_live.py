"""Three-arm evaluation. DEFAULT IS A DRY RUN. Explicit opt-in is mandatory."""
import argparse
import asyncio
import json
import os
import sys
import time
import csv
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kitchen.agent import run_agent, live_model, parse_answer
from kitchen.catalog import recipes
from kitchen.domain import Context
from kitchen.planning import evaluate
from kitchen.settings import require_live


async def single(context,message,before_model=None):
    model=live_model()
    t=time.monotonic()
    try:
        if before_model: before_model()
        async with asyncio.timeout(40):
            response=await model.ainvoke([('system','根据提供的库存、约束和菜谱，一次性给出一至两顿饭计划。不调用工具。最后只输出 JSON，格式：{"status":"ready或no_plan或needs_input","message":"简短说明","plan":{"meals":[{"dishes":[{"recipe_id":"菜谱编号","servings":1}]}]}}；无法完成时 plan 为 null。'),('human',context.model_dump_json()+'\n任务：'+message)])
        answer=parse_answer(response.content)
        report=evaluate(answer.plan,context) if answer.plan else None
        return {**answer.model_dump(mode='json'),'validation':report,'usage':response.usage_metadata,'model_calls':1,'duration_ms':round((time.monotonic()-t)*1000)}
    except Exception as error:
        return {'status':'error','error_type':type(error).__name__,'model_calls':1,'duration_ms':round((time.monotonic()-t)*1000)}


def select_cases(cases, ids=None):
    if ids is None: return cases
    requested=ids.split(',')
    if len(set(requested))!=len(requested): raise ValueError('Repeated case ids are not allowed.')
    known={str(case['id']) for case in cases}
    if set(requested)-known: raise ValueError('Unknown case ids; no model called.')
    return [case for case in cases if str(case['id']) in requested]


async def main(args):
    # A context file contains the same trusted inventory, constraints and recipe pool
    # for all three conditions, frozen before starting the evaluation.
    if not (args.context or args.suite):
        print('DRY RUN ONLY. No model calls. One --context requires up to 13 calls; a --suite needs up to 13 times its case count (20 cases: 260). Explicit approval and --approve-max-calls are mandatory.')
        print('One case: single answer (<=1), tools without replanning (<=6), full agent (<=6). Maximum 13 calls, no retries.')
        return
    if args.context and args.suite: raise SystemExit('Choose --context or --suite, not both.')
    cases=json.loads(Path(args.suite).read_text(encoding='utf-8'))['cases'] if args.suite else [{'id':'01','message':args.message,'context':json.loads(Path(args.context).read_text(encoding='utf-8'))}]
    cases=select_cases(cases,getattr(args,'case_ids',None))
    if not 1<=len(cases)<=20: raise SystemExit('A batch must contain 1–20 cases.')
    if len({str(c['id']) for c in cases})!=len(cases): raise SystemExit('Case ids must be unique.')
    validated=[(case,Context.model_validate(case['context'])) for case in cases]
    if args.approve_max_calls is None:
        print(f'DRY RUN ONLY: cases {[c["id"] for c in cases]}, maximum {13*len(cases)} requests, batch timeout {args.timeout_seconds}s, no retries. Model calls: 0.')
        return
    if args.approve_max_calls != 13*len(cases):
        raise SystemExit(f'This batch requires explicit approval for up to {13*len(cases)} calls. Nothing was called.')
    require_live(True)
    if any(not context.recipes for _,context in validated):
        raise SystemExit('Empty recipe pool. Nothing was called.')
    stamp=str(time.time_ns())
    output=ROOT/'artifacts'/('live-benchmark-'+stamp)
    output.mkdir(parents=True)
    attempts=0
    def charge():
        nonlocal attempts
        if attempts>=args.approve_max_calls: raise PermissionError('Explicit batch request budget exhausted')
        attempts+=1
        (output/'request-budget.json').write_text(json.dumps({'approved_limit':args.approve_max_calls,'attempted':attempts}),encoding='utf-8')
    records=[]
    deadline=time.monotonic()+args.timeout_seconds
    def close(status):
        (output/'batch-report.json').write_text(json.dumps({'status':status,'case_ids':[case['id'] for case in cases],
            'approved_max_calls':args.approve_max_calls,'attempted_requests':attempts,'completed_arm_records':len(records),
            'authorization_closed':True,'unused_requests_not_carried_forward':args.approve_max_calls-attempts},indent=2),encoding='utf-8')
    for index,(case,context) in enumerate(validated,1):
        directory=output/str(index).zfill(2);directory.mkdir()
        (directory/'context.json').write_text(context.model_dump_json(indent=2),encoding='utf-8')
        message=case.get('message',args.message)
        for name,replan in [('single',None),('tools_without_replanning',False),('full_agent',True)]:
            remaining=deadline-time.monotonic()
            if remaining<=0:
                close('timeout');print('Batch timeout; partial results:',output);return
            started_attempts=attempts
            started=time.monotonic()
            try:
                async with asyncio.timeout(remaining):
                    result=await single(context,message,charge) if replan is None else await run_agent(context,message,f'benchmark-{stamp}-{index}-{name}',mode='live',consent=True,allow_replanning=replan,checkpoint_path=directory/'checkpoints.db',before_model=charge)
            except Exception as error:
                result={'status':'error','error_type':type(error).__name__,'model_calls':attempts-started_attempts,'duration_ms':round((time.monotonic()-started)*1000)}
            (directory/(name+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            checks=[e['result'] for e in result.get('trace',[]) if e.get('tool','').endswith('evaluate_plan') and isinstance(e.get('result'),dict)]
            valid=result.get('validation',{}).get('feasible',False) if result.get('validation') else False
            usage=result.get('usage') or {}
            records.append({'case':case['id'],'arm':name,'expected':case.get('expected','unknown'),'status':result['status'],'feasible':valid,'raw_ready_but_invalid':result['status']=='ready' and not valid,'first_check_failed':bool(checks and not checks[0].get('feasible')),'repaired':bool(checks and not checks[0].get('feasible') and valid),'model_calls':result['model_calls'],'input_tokens':usage.get('input_tokens',0),'output_tokens':usage.get('output_tokens',0),'duration_ms':result.get('duration_ms',0)})
            with (output/'summary.csv').open('w',encoding='utf-8-sig',newline='') as f:
                writer=csv.DictWriter(f,fieldnames=list(records[0]));writer.writeheader();writer.writerows(records)
            if result['status']=='error':
                close('stopped_after_error');print('Stopped after error; partial results:',output);return
    close('completed')
    print('Saved real evaluation:',output)
    print('This single case does not establish general superiority; compare success, constraints, latency and token counts.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--context')
    parser.add_argument('--suite',help='Frozen JSON with 1–20 cases; default still makes no calls.')
    parser.add_argument('--case-ids',help='Comma-separated frozen ids for one separately approved batch, e.g. 01,02')
    parser.add_argument('--timeout-seconds',type=int,default=420,choices=range(30,1801),metavar='30..1800')
    parser.add_argument('--approve-max-calls',type=int)
    parser.add_argument('--message',default='请根据已确认库存安排饭菜，优先用掉指定食材。')
    asyncio.run(main(parser.parse_args()))
