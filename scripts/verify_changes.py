"""Frozen photo + sequential demand-change batch. Dry run until separately approved."""
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
from kitchen.domain import Inventory, Preferences, Plan
from kitchen.jobs import Jobs
from kitchen.planning import evaluate, search
from kitchen.proposals import interpret, ProposalConfirmation
from kitchen.settings import require_live
from kitchen.store import Store
from kitchen.vision import identify
from scripts.vision_smoke import select_photo


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def specification():
    return json.loads((ROOT / 'evaluation/change-batch.json').read_text(encoding='utf-8'))


class VerificationFailure(ValueError):
    pass


class BatchBudget:
    def __init__(self, output, limits):
        self.output = output
        self.limits = limits
        self.counts = dict.fromkeys(limits, 0)
        self.stage = None
        self.started = set()

    def enter(self, stage):
        if stage not in self.limits or stage in self.started:
            raise PermissionError('Unknown stage or automatic rerun blocked')
        self.started.add(stage)
        self.stage = stage

    def charge(self):
        if self.stage is None or self.counts[self.stage] >= self.limits[self.stage] or sum(self.counts.values()) >= sum(self.limits.values()):
            raise PermissionError('Authorized batch/stage request budget exhausted')
        self.counts[self.stage] += 1
        write(self.output / 'budget.json', {'limits': self.limits, 'attempts': self.counts, 'total_attempts': sum(self.counts.values())})


def verify_run(result, ctx, expected_status):
    if result['status'] != expected_status:
        raise VerificationFailure(f"Expected {expected_status}, received {result['status']}")
    if result['preferences'] != ctx.preferences.model_dump(mode='json'):
        raise VerificationFailure('Confirmed preferences changed unexpectedly')
    if expected_status == 'ready':
        plan = Plan.model_validate(result['plan'])
        if not evaluate(plan, ctx)['feasible'] or not result.get('validation', {}).get('feasible'):
            raise VerificationFailure('Ready plan failed independent validation')
        if not any(e['kind'] == 'mcp_tool' and e['tool'].endswith('evaluate_plan') and e.get('ok') and e.get('result', {}).get('feasible') for e in result['trace']):
            raise VerificationFailure('Missing passing MCP evaluation')
    else:
        if result.get('plan') is not None or search(ctx, limit=30)['candidates']:
            raise VerificationFailure('No-plan fixture does not match the frozen empty-candidate case')
        if not any(e['kind'] == 'mcp_tool' and e['tool'].endswith('search_recipes') and e.get('ok') for e in result['trace']):
            raise VerificationFailure('No-plan result lacks a real MCP search')


async def workflow(output, mode, budget, spec):
    from kitchen.api import RunRequest
    store = Store(output / 'kitchen.db')
    user, _ = store.new_user()
    saved = store.save_inventory(user, Inventory.model_validate(spec['inventory']))
    store.save_preferences(user, Preferences.model_validate(spec['preferences']))
    original_charge = store.record_model_attempt
    def charge(user_id, kind):
        budget.charge()
        original_charge(user_id, kind)
    store.record_model_attempt = charge
    jobs = Jobs(store)
    results = []

    async def plan(stage, message, previous=None, expected_status='ready'):
        budget.enter(stage)
        prefs = store.preferences(user)
        request = RunRequest(message=message, preferences=prefs, mode=mode, consent=mode == 'live', request_id='frozen-' + stage, expected_revision=previous['revision'] if previous else None)
        started = jobs.start(request, user, previous)
        # Repeated submission must reuse the same task, never send extra model requests.
        repeated = jobs.start(request, user, previous)
        if repeated['id'] != started['id'] or repeated['revision'] != started['revision']:
            raise VerificationFailure('Repeated submission started another revision')
        await asyncio.gather(*list(jobs.tasks))
        result = store.run(user, started['id'])
        write(output / (stage + '.json'), result)
        verify_run(result, store.context(user, prefs), expected_status)
        if store.inventory(user) != saved:
            raise VerificationFailure('Planning changed inventory without consumption confirmation')
        results.append({'stage': stage, 'id': result['id'], 'revision': result['revision'], 'status': result['status'], 'usage': result.get('usage', {}), 'model_calls': result.get('model_calls', 0)})
        return result

    try:
        current = await plan('initial', spec['initial_message'])
        for change in spec['changes']:
            stage = change['id'] + '_intake'
            budget.enter(stage)
            before = store.preferences(user)
            expected = Preferences.model_validate({**before.model_dump(), **change['expected_patch']})
            async with asyncio.timeout(40):
                intake = await interpret(change['message'], before, saved, mode=mode, consent=mode == 'live', before_model=lambda: charge(user, 'intake'), on_response=lambda x: write(output / (stage + '-provider.json'), x))
            write(output / (stage + '.json'), intake)
            if Preferences.model_validate(intake['preferences']) != expected or intake.get('items') or intake.get('questions'):
                raise VerificationFailure('Intake differs from the frozen change; stopped before confirmation')
            proposal = store.create_proposal(user, 'intake', intake, saved.version, before)
            if store.preferences(user) != before or store.inventory(user) != saved:
                raise VerificationFailure('Unconfirmed intake changed state')
            body = ProposalConfirmation(inventory_version=saved.version, preferences=expected)
            # Explicit test-fixture confirmation, isolated from the user's actual kitchen.
            store.confirm_proposal(user, proposal['id'], body)
            if not store.confirm_proposal(user, proposal['id'], body)['already_confirmed']:
                raise VerificationFailure('Confirmation replay was not idempotent')
            old = store.run(user, current['id'])
            if old['status'] == 'ready':
                raise VerificationFailure('Old plan stayed executable after changed preferences')
            write(output / (stage + '-state.json'), {'before': before.model_dump(mode='json'), 'after': expected.model_dump(mode='json'), 'old_plan_status': old['status'], 'inventory_unchanged': store.inventory(user) == saved})
            results.append({'stage': stage, 'usage': intake.get('usage', {}), 'model_calls': intake.get('model_calls', 0)})
            current = await plan(change['id'] + '_replan', change['message'], old, change['expected_status'])
        with store.db() as db:
            revisions = db.execute('SELECT revision FROM run_revisions WHERE run_id=? ORDER BY revision', (current['id'],)).fetchall()
        if [x['revision'] for x in revisions] != [1, 2, 3]:
            raise VerificationFailure('Missing task history revisions')
        write(output / 'workflow-results.json', results)
        return results
    finally:
        await jobs.close()


async def run_batch(approved=None, offline=False):
    spec = specification()
    row, raw = select_photo(spec['photo_id'])
    if not offline and approved != spec['max_requests']:
        return {'status': 'dry_run', 'max_requests': spec['max_requests'], 'limits': spec['limits'], 'photo': {'id': row['id'], 'sha256': row['sha256']}, 'attempted_requests': 0}
    if not offline:
        require_live(True)
    output = ROOT / 'artifacts' / (('change-offline-' if offline else 'change-live-') + str(time.time_ns()))
    output.mkdir(parents=True)
    write(output / 'specification.json', spec)
    write(output / 'code-versions.json', {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ['kitchen/vision.py', 'kitchen/proposals.py', 'kitchen/agent.py', 'kitchen/data/recipes.json']})
    budget = BatchBudget(output, spec['limits'])
    previous_data_dir = os.environ.get('KITCHEN_DATA_DIR')
    os.environ['KITCHEN_DATA_DIR'] = str(output / 'runtime')
    report = {'mode': 'offline' if offline else 'live', 'directory': str(output), 'photo_skipped': offline}
    try:
        async with asyncio.timeout(420):
            if not offline:
                budget.enter('photo')
                write(output / 'photo-input.json', {'id': row['id'], 'sha256': row['sha256'], 'source': row['source']})
                async with asyncio.timeout(40):
                    observation = await identify([raw], True, before_model=budget.charge, on_response=lambda x: write(output / 'photo-provider.json', x))
                write(output / 'photo-observations.json', observation)
                report['photo_usage'] = observation.get('usage', {})
            report['workflow'] = await workflow(output, report['mode'], budget, spec)
            report['status'] = 'completed'
    except Exception as error:
        report.update(status='failed', stage=budget.stage, error_type=type(error).__name__)
        if isinstance(error, VerificationFailure):
            report['reason'] = str(error)
        if isinstance(error, ValidationError):
            report['validation_errors'] = [{'location': list(x['loc']), 'type': x['type']} for x in error.errors()]
        if isinstance(error, httpx.HTTPStatusError):
            report['http_status'] = error.response.status_code
    finally:
        if previous_data_dir is None:
            os.environ.pop('KITCHEN_DATA_DIR', None)
        else:
            os.environ['KITCHEN_DATA_DIR'] = previous_data_dir
    report.update(attempted_requests=sum(budget.counts.values()), stage_attempts=budget.counts)
    write(output / 'report.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--approve-max-calls', type=int, choices=[21])
    mode.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    result = asyncio.run(run_batch(args.approve_max_calls, args.offline))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if result['status'] == 'failed' else 0)
