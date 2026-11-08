import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from kitchen import vision
from test_vision import picture


@pytest.mark.asyncio
async def test_recorded_format_tag_is_compatible_without_inventing_inventory(monkeypatch):
    fixture=json.loads((Path(__file__).parent/'fixtures/vision-veg-fridge-format-tag.json').read_text(encoding='utf-8'))
    original=httpx.AsyncClient
    def handler(request):
        return httpx.Response(200,json=fixture)
    monkeypatch.setattr(vision.httpx,'AsyncClient',lambda **kw:original(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setenv('KITCHEN_ENABLE_LIVE','1')
    monkeypatch.setenv('DEEPSEEK_API_KEY','unit-test-not-a-real-key')
    result=await vision.identify(picture(),True)
    assert len(result['items'])==15 and result['parse_warnings']
    assert result['requires_confirmation']
    assert all(x['suggested_quantity'] is None for x in result['items'])
    # The original model guessed eight eggs in a closed box; it is NOT a correct count.
    egg=next(x for x in result['items'] if x['suggested_ingredient_id']=='egg')
    assert egg['obscured'] and egg['suggested_quantity'] is None


@pytest.mark.parametrize('payload',[
    {'type':'tool_call','items':[]},
    {'type':'json_object','items':[],'update_inventory':True},
    {'type':'json_object','items':[{'name':'egg','quantity':999}]},
    {'type':'json_object','items':[{'name':'egg','visible_count':-1}]},
    {'type':'json_object','items':[{'name':'milk','package_unit':'litres'}]}
])
def test_format_compatibility_keeps_unknown_fields_and_invalid_food_data_rejected(payload):
    with pytest.raises(ValidationError):
        vision.parse_observations(json.dumps(payload))
