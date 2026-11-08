from fastapi.testclient import TestClient
from kitchen.api import create_app

HEADERS={"X-Kitchen-Client":"fridge-web"}


def test_session_isolation_csrf_and_live_gate(tmp_path):
    app=create_app(tmp_path/"api.db")
    with TestClient(app) as a,TestClient(app) as b:
        assert a.post('/api/session').status_code==403
        assert a.post('/api/session',headers={**HEADERS,"Origin":"https://evil.example"}).status_code==403
        a.post('/api/session',headers=HEADERS)
        b.post('/api/session',headers=HEADERS)
        stock={"items":[{"ingredient_id":"egg","quantity":3,"unit":"piece"}],"pantry":[],"version":0}
        assert a.put('/api/inventory',headers=HEADERS,json=stock).status_code==200
        assert b.get('/api/inventory').json()['items']==[]
        assert a.put('/api/inventory',headers=HEADERS,json=stock).status_code==409
        prefs=a.post('/api/session',headers=HEADERS).json()['preferences']
        response=a.post('/api/runs',headers=HEADERS,json={"message":"test","preferences":prefs,"mode":"live","consent":True})
        assert response.status_code==403
        assert a.get('/api/inventory').headers['cache-control']=='no-store'


def test_vision_disabled_without_upload_to_provider(tmp_path):
    with TestClient(create_app(tmp_path/"api.db")) as client:
        client.post('/api/session',headers=HEADERS)
        response=client.post('/api/vision',headers=HEADERS,data={"consent":"true"},files={"file":("image.jpg",b"not image","image/jpeg")})
        assert response.status_code==403
