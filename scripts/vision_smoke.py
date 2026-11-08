"""One explicitly approved public-photo request; defaults to local-only dry run."""
import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from kitchen import vision
from kitchen.settings import require_live


def select_photo(image_id):
    manifest = json.loads((ROOT / 'evaluation/web-photo-manifest.json').read_text(encoding='utf-8'))
    row = next((x for x in manifest['images'] if x['id'] == image_id), None)
    if not row or row.get('evaluation_status') != 'selected':
        raise ValueError('Choose a selected photo from the reviewed manifest')
    path = (ROOT / row['path']).resolve()
    if not path.is_relative_to((ROOT / 'evaluation/photos').resolve()):
        raise ValueError('Photo path is outside the local evaluation directory')
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise ValueError('Photo changed since review; inspect it and renew the manifest first')
    vision.prepare_image(raw)  # Validate locally, without uploading or saving a derivative.
    return row, raw


async def run_smoke(image_id='gfp01', approved=None):
    row, raw = select_photo(image_id)
    summary = {'image_id': row['id'], 'source': row['source'], 'sha256': row['sha256'],
               'images': 1, 'max_requests': 1, 'max_output_tokens': 3000,
               'timeout_seconds': 40, 'automatic_retries': 0, 'inventory_updates': 0}
    if approved != 1:
        return {**summary, 'status': 'dry_run', 'attempted_requests': 0}
    require_live(True)
    output = ROOT / 'artifacts' / ('vision-smoke-' + str(time.time_ns()))
    output.mkdir(parents=True)
    (output / 'input.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    attempts = 0
    provider = {}

    def capture(response):
        provider.update(response)
        (output / 'provider-result.json').write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding='utf-8')

    def charge():
        nonlocal attempts
        if attempts >= 1:
            raise PermissionError('Authorized request budget exhausted')
        attempts += 1
        (output / 'budget.json').write_text(json.dumps({'approved': 1, 'attempted': attempts}), encoding='utf-8')

    started = time.monotonic()
    try:
        async with asyncio.timeout(40):
            result = await vision.identify([raw], True, before_model=charge, on_response=capture)
        (output / 'observations.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        report = {**summary, 'status': 'completed', 'usage': result.get('usage', {}),
                  'observation_count': len(result['items']), 'requires_confirmation': result['requires_confirmation']}
    except Exception as error:
        # Never persist request headers, image base64, API keys or arbitrary provider error text.
        report = {**summary, 'status': 'failed', 'error_type': type(error).__name__}
        if isinstance(error, httpx.HTTPStatusError):
            report['http_status'] = error.response.status_code
        if isinstance(error, ValidationError):
            report['validation_errors'] = [{'location': list(e['loc']), 'type': e['type'], 'message': e['msg'][:300]} for e in error.errors()]
        if provider:
            report['usage'] = provider.get('usage', {})
            report['finish_reason'] = provider.get('finish_reason')
    report.update(attempted_requests=attempts, duration_ms=round((time.monotonic()-started)*1000), directory=str(output))
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image-id', default='gfp01')
    parser.add_argument('--approve-max-calls', type=int, choices=[1])
    args = parser.parse_args()
    result = asyncio.run(run_smoke(args.image_id, args.approve_max_calls))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1 if result['status'] == 'failed' else 0)
