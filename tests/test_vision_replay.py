"""Replay a recorded model response through the real API, without any paid request."""
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from kitchen import vision
from kitchen.api import create_app
from test_vision import picture

HEADERS = {'X-Kitchen-Client': 'fridge-web'}


def test_recorded_photo_requires_manual_confirmation_and_preserves_unseen(tmp_path, monkeypatch):
    response = json.loads((Path(__file__).parent / 'fixtures/vision-gfp01-response.json').read_text(encoding='utf-8'))
    original = httpx.AsyncClient
    requests = []
    def provider(request):
        requests.append(request)
        return httpx.Response(200, json=response)
    monkeypatch.setattr(vision.httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(provider), **kw))
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE', '1')
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'unit-test-not-a-real-key')
    with TestClient(create_app(tmp_path / 'replay.db')) as client:
        client.post('/api/session', headers=HEADERS).raise_for_status()
        stock = client.put('/api/inventory', headers=HEADERS, json={'version': 0, 'items': [{'ingredient_id': 'egg', 'quantity': 3, 'unit': 'piece'}], 'pantry': []}).json()
        # White test image + captured text response: tests API handling, not vision accuracy.
        result = client.post('/api/vision', headers=HEADERS, data={'consent': 'true', 'purpose': 'stocktake'}, files=[('files', ('fixture.png', picture(), 'image/png'))])
        result.raise_for_status()
        proposal = result.json()
        assert proposal['requires_confirmation']
        assert all(x['suggested_quantity'] is None for x in proposal['items'])
        milk = next(x for x in proposal['items'] if x['ingredient_id'] == 'milk')
        assert milk['obscured'] and milk['unit'] == 'ml'
        assert client.get('/api/inventory').json() == stock
        confirmation = {'inventory_version': proposal['inventory_version'], 'changes': [{'ingredient_id': 'milk', 'quantity': 250, 'unit': 'ml', 'action': 'set', 'identity_confirmed': True}]}
        # 250 ml is a synthetic user confirmation; never a claimed quantity in the public photo.
        first = client.post('/api/proposals/' + proposal['id'] + '/confirm', headers=HEADERS, json=confirmation)
        first.raise_for_status()
        repeated = client.post('/api/proposals/' + proposal['id'] + '/confirm', headers=HEADERS, json=confirmation)
        assert repeated.json()['already_confirmed']
        inventory = client.get('/api/inventory').json()
        assert {x['ingredient_id']: x['quantity'] for x in inventory['items']} == {'egg': '3', 'milk': '250'}
        assert inventory['version'] == first.json()['inventory']['version']
    assert len(requests) == 1
