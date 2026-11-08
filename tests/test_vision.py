import io
import json
import httpx
import pytest
from PIL import Image
from kitchen import vision


def picture():
    image=Image.new('RGB',(20,20),'white')
    out=io.BytesIO();image.save(out,format='PNG');return out.getvalue()


def test_image_format_and_size():
    assert vision.prepare_image(picture()).startswith('data:image/jpeg;base64,')
    with pytest.raises(ValueError):vision.prepare_image(b'not an image')
    with pytest.raises(ValueError):vision.prepare_image(b'x'*(8*1024*1024+1))


@pytest.mark.asyncio
async def test_vision_contract_mock_only(monkeypatch):
    original=httpx.AsyncClient
    def handler(request):
        body=json.loads(request.content)
        assert body['model']=='deepseek-flash'
        assert body['messages'][0]['content'][1]['image_url']['url'].startswith('data:image/jpeg;base64,')
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'items':[{'name':'鸡蛋','ingredient_id':'egg','visible_count':3,'note':'仍需确认'},{'name':'不确定食材','ingredient_id':'invented','visible_count':None,'note':'请人工识别'}],'note':'请确认实际分量'})}}],'usage':{'total_tokens':123}})
    monkeypatch.setattr(vision.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setenv('DEEPSEEK_API_KEY','unit-test-not-a-real-key')
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE','1')
    result=await vision.identify(picture(),True)
    assert result['requires_confirmation']
    assert result['items'][0]['visible_count']==3
    assert result['items'][1]['ingredient_id'] is None


@pytest.mark.asyncio
async def test_vision_denied_before_request():
    with pytest.raises(PermissionError):await vision.identify(picture(),True)
