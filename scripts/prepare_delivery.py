"""Generate blank team materials and an allowlisted source archive. Never calls models."""
import argparse
import hashlib
import html
import json
import sys
import time
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from kitchen.catalog import ingredients

PHOTO_SCENARIOS=[
    '整箱清晰、少量食材','多层冰箱分层拍摄','鸡蛋等可计数食材','净含量清晰的未开封包装',
    '已开封包装与剩余比例','散装蔬菜，无重量参照','遮挡或不透明盒袋',
    '同一物品跨照片重复出现','同类食材的两个独立包装','账面库存与实际剩余不一致',
]


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def source_files(root=ROOT):
    """Explicit allowlist; no environment, databases, photos, receipts or logs."""
    top=['README.md','pyproject.toml','requirements.lock.txt','Dockerfile','render.yaml','.dockerignore','.gitignore','.gitattributes','.env.example','启动本地项目.cmd']
    files=[root/name for name in top if (root/name).is_file()]
    for folder,extensions in [('kitchen',{'.py','.json'}),('scripts',{'.py','.ps1'}),('tests',{'.py','.json'}),('docs',{'.md'})]:
        files.extend(p for p in (root/folder).rglob('*') if p.is_file() and p.suffix in extensions and '__pycache__' not in p.parts)
    files.extend(p for p in (root/'frontend').iterdir() if p.is_file() and p.suffix in {'.json','.html','.ts'})
    for name in ['frontend/src','frontend/public','frontend/e2e']:
        files.extend(p for p in (root/name).rglob('*') if p.is_file() and p.suffix in {'.ts','.tsx','.js','.css','.json','.svg','.html','.webmanifest'})
    files.extend(p for p in (root/'evaluation').glob('*.json') if p.is_file())
    return sorted({p for p in files if not p.is_symlink()})


def review_html(recipes):
    names={key:value.name for key,value in ingredients().items()}
    escape=lambda value:html.escape(str(value))
    cards=[]
    for r in recipes:
        amounts='、'.join(f"{names.get(i['ingredient_id'],i['ingredient_id'])} {i['quantity']} {i['unit']}" for i in r['ingredients'])
        profiles=''.join('<tr><td>'+str(n)+'</td><td>'+str(r['serving_profiles'][str(n)]['minutes'])+'</td><td>'+str(r['serving_profiles'][str(n)]['batches'])+'</td><td>'+escape(r['serving_profiles'][str(n)]['instructions'])+'</td></tr>' for n in range(1,6))
        steps=''.join('<li>'+escape(s)+'</li>' for s in r['steps'])
        cards.append(f"""<article><small>{escape(r['id'])} · 配方版本 {r.get('version',1)}</small><h2>{escape(r['name'])}</h2>
<p>当前团队审核状态：{'已标记审核（仍需核对记录）' if r.get('team_reviewed') else '未审核'}；记录的实做次数：{r.get('cooked_count',0)}</p>
<p>基础人数：{r.get('base_servings',1)}；用料：{escape(amounts)}</p><p>厨具：{escape('、'.join(r['equipment']))}；调料：{escape('、'.join(r['pantry']))}</p>
<p>来源：{escape(r['source_label'])}</p><ol>{steps}</ol><table><tr><th>人数</th><th>预计分钟</th><th>批数</th><th>分批说明</th></tr>{profiles}</table>
<p class="blank">审核人 / 日期：________________　来源核对：________________</p><p class="blank">用量、时间、步骤修订：________________________________________________</p><p class="blank">实做记录编号（未实做留空）：________________</p></article>""")
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>余味 · 菜谱审核工作册</title><style>body{font:16px/1.6 system-ui;color:#253c30;max-width:1000px;margin:32px auto;padding:20px;background:#f7f8f0}article{background:white;border:1px solid #d2dacb;padding:24px;margin:24px 0;break-inside:avoid}table{border-collapse:collapse;width:100%}td,th{border:1px solid #d2dacb;padding:8px;text-align:left}.blank{line-height:2.2}small{color:#637159}@media print{body{background:white;font-size:11px;margin:0}article{break-after:page;border:0}}</style><h1>余味 · 菜谱审核工作册</h1><p>这是现有配方的审核工作稿，不是通过审核的证明。未审核的时间与分批表为开发估计；先审核5–10道常用菜，再扩展。用浏览器打印可保存PDF。修改记入 recipes-working-copy.json，使用 review_recipes.py 检查后由开发者导入。实做次数只填写真实记录。</p>'+''.join(cards)+'</html>'


def prepare(output):
    output.mkdir(parents=True,exist_ok=False)
    recipes=json.loads((ROOT/'kitchen/data/recipes.json').read_text(encoding='utf-8'))
    write_json(output/'recipes-working-copy.json',recipes)
    (output/'recipe-review.html').write_text(review_html(recipes),encoding='utf-8')
    for n,title in enumerate(PHOTO_SCENARIOS,1):
        write_json(output/'photo-records'/f'{n:02}.json',{
            'scenario_id':f'{n:02}','scenario':title,'status':'pending','participant_code':None,
            'independent_fridge_code':None,'permission_to_use':False,'permission_to_upload':False,
            'captured_at':None,'images':[],
            'inventory_truth':[],
            'truth_item_fields':{'object_id':'同一物品跨图用同一个编号','ingredient_id':'目录ID或unknown','quantity':None,'unit':'g/ml/piece','measurement_method':'称重/点数/包装标签','image_indices':[],'visible_count':None,'obscured':None,'package_label':None,'sealed':None},
            'response_artifact':None,'reviewer':None,
            'evaluation':{'identity_errors':None,'count_errors':None,'label_errors':None,'duplicate_errors':None,'unsupported_quantity_suggestions':None,'manual_edits':None,'confirmation_seconds':None},
            'notes':'先记录实物真值再运行模型；留空不代表零错误。图片上传另行按批授权。',
        })
    for n in range(1,6):
        write_json(output/'cooking-records'/f'{n:02}.json',{
            'record_id':f'cook-{n:02}','status':'pending','cook_code':None,'date':None,
            'diners':None,'recipe_ids':[],'recipe_versions':{},'equipment':[],
            'actual_ingredients':[],'remaining_inventory':[],
            'planned_minutes':None,'actual_minutes':None,'actual_batches':None,
            'taste_1_to_5':None,'difficulty_1_to_5':None,'serving_sufficiency':None,
            'changes_to_recipe':None,'notes':None,
        })
        write_json(output/'user-records'/f'{n:02}.json',{
            'participant_code':f'P{n:02}','status':'pending','consent_to_use_anonymized_results':False,
            'date':None,'device':None,'network':None,'run_ids':[],
            'completed_photo_confirmation':None,'completed_plan':None,'completed_requirement_change':None,
            'completed_consumption_confirmation':None,'total_seconds':None,
            'moderator_help_count':None,'photo_edits':None,'difficulties':None,'feedback':None,
            'note':'熟人即可；不填写姓名、账号或联系方式。不诱导正面评价。',
        })
    paths=source_files()
    with zipfile.ZipFile(output/'source-only.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in paths: archive.write(path,path.relative_to(ROOT).as_posix())
    write_json(output/'source-manifest.json',{'files':{p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},'notice':'仅源码，不含密钥、数据库、照片、环境或生成的评估结果；未上传。'})
    (output/'START_HERE.txt').write_text('先打开 recipe-review.html。菜谱负责人修改 recipes-working-copy.json 并填写 cooking-records；照片与试用负责人填写 photo-records 和 user-records。全部记录初始为pending，不是实验结果。运行 scripts/review_recipes.py 工作稿路径 只校验结构，不自动认证审核。source-only.zip 是部署候选源码，尚未上传或发布。详见项目 docs/TEAM_HANDOFF.md 和 docs/EVALUATION_PROTOCOL.md。\n',encoding='utf-8')
    return output


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'artifacts'/('team-kit-'+str(time.time_ns())))
    args=parser.parse_args()
    print(prepare(args.output.resolve()))
