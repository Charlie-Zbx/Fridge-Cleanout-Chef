import json

import httpx
import pytest

from scripts import vision_smoke


@pytest.fixture
def smoke(monkeypatch, tmp_path):
    monkeypatch.setattr(vision_smoke, 'ROOT', tmp_path)
    monkeypatch.setattr(vision_smoke, 'select_photo', lambda _: ({'id': 'fixture', 'source': 'local mock', 'sha256': 'mock'}, b'mock-image'))
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE', '1')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'unit-test-not-a-real-key')
    return vision_smoke


@pytest.mark.asyncio
async def test_dry_run_cannot_send_even_with_live_enabled(smoke, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError('Dry run must not call the image provider')
    monkeypatch.setattr(smoke.vision, 'identify', forbidden)
    report = await smoke.run_smoke()
    assert report['status'] == 'dry_run' and report['attempted_requests'] == 0
    assert not (smoke.ROOT / 'artifacts').exists()


@pytest.mark.asyncio
async def test_failed_request_counts_once_and_is_not_retried(smoke, monkeypatch):
    calls = []
    async def failed(raw, consent, before_model, on_response=None):
        before_model()
        calls.append(raw)
        request = httpx.Request('POST', 'https://example.invalid')
        response = httpx.Response(429, request=request)
        raise httpx.HTTPStatusError('Do not write arbitrary provider text', request=request, response=response)
    monkeypatch.setattr(smoke.vision, 'identify', failed)
    report = await smoke.run_smoke(approved=1)
    assert len(calls) == 1
    assert report['status'] == 'failed' and report['attempted_requests'] == 1
    assert report['http_status'] == 429
    assert 'arbitrary' not in json.dumps(report)


@pytest.mark.asyncio
async def test_request_budget_blocks_second_attempt(smoke, monkeypatch):
    async def accidental_retry(raw, consent, before_model, on_response=None):
        before_model()
        before_model()
    monkeypatch.setattr(smoke.vision, 'identify', accidental_retry)
    report = await smoke.run_smoke(approved=1)
    assert report['error_type'] == 'PermissionError'
    assert report['attempted_requests'] == 1


@pytest.mark.asyncio
async def test_invalid_model_output_preserves_usage_and_field_diagnostics(smoke, monkeypatch):
    from test_vision import picture
    monkeypatch.setattr(smoke, 'select_photo', lambda _: ({'id': 'fixture', 'source': 'local mock', 'sha256': 'mock'}, picture()))
    original = httpx.AsyncClient
    calls = []
    def provider(request):
        calls.append(request)
        return httpx.Response(200, json={'model': 'mock', 'choices': [{'finish_reason': 'stop', 'message': {'content': '{"items":[{"name":"milk","note":null}]}'}}], 'usage': {'total_tokens': 123}})
    monkeypatch.setattr(smoke.vision.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(provider), **kw))
    report = await smoke.run_smoke(approved=1)
    assert len(calls) == 1 and report['attempted_requests'] == 1
    assert report['status'] == 'failed' and report['usage']['total_tokens'] == 123
    assert report['validation_errors'][0]['location'] == ['items', 0, 'note']
    recorded = (smoke.ROOT / 'artifacts').glob('*/provider-result.json')
    contents = next(recorded).read_text(encoding='utf-8')
    assert 'null' in contents and 'unit-test-not-a-real-key' not in contents
    assert 'data:image' not in contents and 'Authorization' not in contents
