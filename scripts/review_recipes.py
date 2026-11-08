"""Validate a team-edited recipe library; optional explicit import, never AI approval."""
import argparse
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kitchen.domain import Recipe
from kitchen.catalog import ingredients, PANTRY, EQUIPMENT


def validate(path):
    values=[Recipe.model_validate(x) for x in json.loads(path.read_text(encoding='utf-8'))]
    if len({r.id for r in values})!=len(values): raise ValueError('配方编号重复')
    for r in values:
        if set(r.serving_profiles)!={'1','2','3','4','5'}: raise ValueError(f'{r.id}:必须填写1–5人份时间和分批说明')
        if len({x.ingredient_id for x in r.ingredients})!=len(r.ingredients): raise ValueError(f'{r.id}:配方食材重复')
        for item in r.ingredients:
            if item.ingredient_id not in ingredients() or item.unit!=ingredients()[item.ingredient_id].unit: raise ValueError(f'{r.id}:食材或单位错误')
        if set(r.pantry)-PANTRY.keys() or set(r.equipment)-EQUIPMENT.keys(): raise ValueError(f'{r.id}:调料或厨具不在目录')
        if r.team_reviewed and not all([r.team_reviewed_by,r.team_reviewed_at,r.source_label]): raise ValueError(f'{r.id}:团队审核需填写审核人、日期和来源')
        if r.cooked_count!=len(r.cooking_records): raise ValueError(f'{r.id}:实做次数必须与记录编号对应')
    return values


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file',type=Path)
    parser.add_argument('--import-confirmed-team-library',action='store_true')
    args=parser.parse_args()
    values=validate(args.file)
    print(f'{len(values)} recipes structurally valid. This check does NOT certify taste or human review.')
    if args.import_confirmed_team_library:
        target=ROOT/'kitchen/data/recipes.json'
        previous={r['id']:r for r in json.loads(target.read_text(encoding='utf-8'))}
        for r in values:
            old=previous.get(r.id)
            if old and r.model_dump(mode='json')!=Recipe.model_validate(old).model_dump(mode='json'):
                r.version=max(r.version,old.get('version',1)+1)
        target.write_text(json.dumps([r.model_dump(mode='json') for r in values],ensure_ascii=False,indent=2),encoding='utf-8')
        print('Imported; restart server. Personal approvals for older recipe versions will expire.')
