"""Reproducible AI-drafted fixtures; this does not certify any recipe as reviewed/cooked."""
import json
import argparse
import math
parser=argparse.ArgumentParser()
parser.add_argument("--replace-unreviewed-fixtures",action="store_true")
args=parser.parse_args()
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "kitchen" / "data"
ROOT.mkdir(parents=True, exist_ok=True)
if (ROOT/"recipes.json").exists() and not args.replace_unreviewed_fixtures:
    raise SystemExit("Recipe library exists. Refusing to overwrite; --replace-unreviewed-fixtures is only for deliberately resetting development fixtures.")
rows = [
    ("egg","鸡蛋","piece",["egg"],["鸡子"]),
    ("cabbage","卷心菜","g",[],["包菜","圆白菜"]),
    ("tofu","豆腐","g",["soy"],[]),
    ("tomato","番茄","g",[],["西红柿"]),
    ("potato","土豆","g",[],["马铃薯"]),
    ("carrot","胡萝卜","g",[],[]),
    ("cucumber","黄瓜","g",[],[]),
    ("mushroom","鲜蘑菇","g",[],["蘑菇"]),
    ("pepper","青椒","g",[],[]),
    ("onion","洋葱","g",[],[]),
    ("zucchini","西葫芦","g",[],[]),
    ("broccoli","西兰花","g",[],[]),
    ("spinach","菠菜","g",[],[]),
    ("lettuce","生菜","g",[],[]),
    ("cooked_rice","熟米饭","g",[],["剩米饭"]),
    ("rice","生大米","g",[],["大米"]),
    ("noodles","干面条","g",["wheat"],["面条"]),
    ("chicken","鸡肉","g",[],[]),
    ("pork","猪肉","g",[],[]),
    ("beef","牛肉","g",[],[]),
    ("shrimp","虾仁","g",["shellfish"],[]),
    ("fish","鱼片","g",["fish"],[]),
    ("milk","牛奶","ml",["milk"],[]),
    ("corn","玉米粒","g",[],[]),
    ("eggplant","茄子","g",[],[]),
    ("garlic","大蒜","g",[],["蒜"]),
    ("ginger","生姜","g",[],["姜"]),
    ("scallion","小葱","g",[],["葱"]),
    ("bok_choy","小白菜","g",[],["白菜苗"]),
    ("pumpkin","南瓜","g",[],[]),
]
catalog = [{"id":i,"name":n,"unit":u,"allergens":a,"aliases":als} for i,n,u,a,als in rows]
units = {x["id"]:x["unit"] for x in catalog}
# Quantities are for one diner; time is a conservative draft estimate for up to two.
specs = [
 ("cabbage_egg","卷心菜炒蛋",[("cabbage",100),("egg",2)],15,"pan",["oil","salt"],"卷心菜洗净切丝；鸡蛋打散。|锅中放少量油，炒熟鸡蛋后盛出。|炒熟卷心菜，加入鸡蛋和少量盐拌匀。"),
 ("pan_tofu","香煎豆腐",[("tofu",150)],18,"pan",["oil","salt"],"豆腐沥水后切厚片。|平底锅放少量油，中小火煎豆腐，定型后翻面。|煎至两面上色并充分加热，撒少量盐。"),
 ("tomato_egg","番茄炒蛋",[("tomato",150),("egg",2)],15,"pan",["oil","salt"],"番茄洗净切块，鸡蛋打散。|先将鸡蛋炒熟盛出。|炒软番茄，加入鸡蛋拌匀，以少量盐调味。"),
 ("stir_cabbage","清炒卷心菜",[("cabbage",150)],12,"pan",["oil","salt"],"卷心菜洗净沥水，切成小片。|锅中放油，加入卷心菜翻炒。|炒熟后加少量盐拌匀。"),
 ("tomato_tofu","番茄炖豆腐",[("tomato",150),("tofu",150)],20,"pot",["oil","salt"],"番茄切块，豆腐切小块。|锅中少量油炒软番茄，加入适量水。|放入豆腐煮至充分加热，加入少量盐。"),
 ("egg_cucumber","黄瓜炒蛋",[("cucumber",150),("egg",2)],15,"pan",["oil","salt"],"黄瓜洗净切片，鸡蛋打散。|炒熟鸡蛋后盛出。|黄瓜翻炒至熟，加入鸡蛋和盐拌匀。"),
 ("potato_strips","清炒土豆丝",[("potato",180)],20,"pan",["oil","salt"],"土豆去皮切细丝，冲洗并沥干。|锅中放少量油，炒土豆丝，必要时加少量水。|炒至完全熟透后调味。"),
 ("carrot_egg","胡萝卜炒蛋",[("carrot",120),("egg",2)],18,"pan",["oil","salt"],"胡萝卜洗净切细丝，鸡蛋打散。|先炒熟鸡蛋盛出。|炒熟胡萝卜，加入鸡蛋和盐拌匀。"),
 ("mushroom_tofu","蘑菇豆腐汤",[("mushroom",100),("tofu",150)],20,"pot",["salt"],"使用确认可食用的鲜蘑菇，洗净切片；豆腐切块。|锅中加水，煮熟蘑菇。|加入豆腐充分煮热后加少量盐。"),
 ("pepper_egg","青椒炒蛋",[("pepper",120),("egg",2)],15,"pan",["oil","salt"],"青椒去籽切丝，鸡蛋打散。|鸡蛋炒熟后盛出。|青椒炒熟，加入鸡蛋和盐拌匀。"),
 ("onion_egg","洋葱炒蛋",[("onion",120),("egg",2)],15,"pan",["oil","salt"],"洋葱切丝，鸡蛋打散。|鸡蛋炒熟后盛出。|炒软洋葱，加入鸡蛋和盐拌匀。"),
 ("zucchini_egg","西葫芦炒蛋",[("zucchini",150),("egg",2)],18,"pan",["oil","salt"],"西葫芦洗净切片，鸡蛋打散。|鸡蛋炒熟盛出。|炒熟西葫芦，加入鸡蛋与盐拌匀。"),
 ("garlic_broccoli","蒜蓉西兰花",[("broccoli",180),("garlic",5)],18,"pan",["oil","salt"],"西兰花切小朵洗净，蒜切末。|锅中少量油炒香蒜末，加入西兰花翻炒。|加少量水加盖焖熟，再用盐调味。"),
 ("stir_spinach","清炒菠菜",[("spinach",180)],12,"pan",["oil","salt"],"菠菜洗净，切去老根。|锅中放少量油，翻炒菠菜。|充分炒熟后加少量盐。"),
 ("garlic_lettuce","蒜蓉生菜",[("lettuce",180),("garlic",5)],12,"pan",["oil","salt"],"生菜洗净沥水，蒜切末。|锅中少量油炒香蒜末，加入生菜。|炒熟后加少量盐拌匀。"),
 ("egg_rice","蛋炒饭",[("cooked_rice",180),("egg",1)],15,"pan",["oil","salt"],"确认熟米饭适合食用，打散结块；鸡蛋打散。|锅中放少量油，将鸡蛋炒熟。|加入米饭炒散，充分加热后调味。"),
 ("cabbage_rice","卷心菜蛋炒饭",[("cooked_rice",180),("cabbage",80),("egg",1)],20,"pan",["oil","salt"],"确认熟米饭适合食用；卷心菜切丝，鸡蛋打散。|炒熟鸡蛋和卷心菜。|加入米饭炒散并充分加热，加盐调味。"),
 ("tomato_noodles","番茄鸡蛋面",[("noodles",80),("tomato",120),("egg",1)],25,"pot",["oil","salt"],"番茄切块，鸡蛋打散。|锅中少量油炒熟鸡蛋与番茄，加入水煮开。|加入面条煮至熟透，按口味放少量盐。"),
 ("cabbage_noodles","卷心菜汤面",[("noodles",80),("cabbage",120)],20,"pot",["salt"],"卷心菜洗净切丝。|锅中加水煮开，放入面条和卷心菜。|煮至面条和蔬菜熟透，加少量盐。"),
 ("broccoli_chicken","西兰花炒鸡肉",[("broccoli",150),("chicken",120)],25,"pan",["oil","salt"],"鸡肉切小片，生熟器具分开；西兰花洗净切小朵。|锅中放油，炒鸡肉至充分熟透。|加入西兰花和少量水，加盖焖熟后调味。"),
 ("pepper_pork","青椒炒肉丝",[("pepper",120),("pork",100)],25,"pan",["oil","soy_sauce"],"猪肉切细丝，生熟器具分开；青椒去籽切丝。|锅中放油，将肉丝炒至充分熟透。|加入青椒炒熟，加少量酱油。"),
 ("onion_beef","洋葱炒牛肉",[("onion",120),("beef",100)],25,"pan",["oil","soy_sauce"],"牛肉切薄片，生熟器具分开；洋葱切丝。|锅中放油，将牛肉炒熟。|加入洋葱炒软，确保肉充分熟透后调味。"),
 ("shrimp_egg","虾仁炒蛋",[("shrimp",100),("egg",2)],20,"pan",["oil","salt"],"处理好的虾仁沥水，鸡蛋打散，生熟器具分开。|锅中放少量油，将虾仁炒至熟透。|加入蛋液，炒至完全凝固并调味。"),
 ("fish_tofu","鱼片豆腐汤",[("fish",120),("tofu",120),("ginger",5)],25,"pot",["salt"],"鱼片检查鱼刺，生熟器具分开；豆腐切块，姜切片。|水中加入姜和豆腐煮开。|加入鱼片煮至完全熟透后调味。"),
 ("corn_carrot","玉米胡萝卜丁",[("corn",100),("carrot",100)],18,"pan",["oil","salt"],"胡萝卜洗净切小丁，玉米粒洗净。|锅中放少量油，翻炒胡萝卜与玉米。|加少量水焖至熟透后调味。"),
 ("eggplant_potato","茄子烧土豆",[("eggplant",120),("potato",120)],30,"pan",["oil","soy_sauce"],"茄子切块，土豆去皮切小块。|锅中放油翻炒土豆和茄子。|加入适量水和少量酱油，焖至全部熟透。"),
 ("bok_choy_tofu","小白菜豆腐汤",[("bok_choy",150),("tofu",150)],18,"pot",["salt"],"小白菜洗净切段，豆腐切块。|锅中加水，煮热豆腐。|加入小白菜煮熟，放少量盐。"),
 ("steamed_pumpkin","清蒸南瓜",[("pumpkin",200)],25,"steamer",[],"南瓜去籽，洗净切均匀小块。|蒸锅加水，放入装南瓜的耐热盘。|蒸至南瓜熟软，取出时防烫。"),
 ("steamed_egg","蒸水蛋",[("egg",2)],25,"steamer",["salt"],"鸡蛋打散，加约蛋液1.5倍温水和少量盐。|蛋液放入耐热容器，盖上耐热盖。|放入蒸锅蒸至完全凝固，时间按容器调整。"),
 ("plain_rice","电饭煲米饭",[("rice",80)],45,"rice_cooker",[],"大米淘洗后放入电饭煲。|按电饭煲刻度和说明加入适量水。|使用煮饭程序，完成后焖片刻再盛出。"),
]
recipes = [{"id":i,"name":n,"ingredients":[{"ingredient_id":k,"quantity":q,"unit":units[k]} for k,q in ing],"pantry":pantry,"equipment":[eq],"minutes":minutes,"steps":steps.split("|"),"tags":["家常"],"source_label":"AI 起草的开发示例；用时与口味未经实做验证","reviewed":False,"cooked_count":0} for i,n,ing,minutes,eq,pantry,steps in specs]
for recipe in recipes:
    recipe.update(base_servings=1,count_rounding='ceil',version=2,team_reviewed=False,team_reviewed_by=None,team_reviewed_at=None,cooking_records=[])
    recipe['serving_profiles']={str(n):{'minutes':recipe['minutes'] if n<=2 else recipe['minutes']*math.ceil(n/2)+3*(n-2),'batches':math.ceil(n/2),'instructions':f'开发估计，待团队审核：{n}人份分{math.ceil(n/2)}批顺序制作；每批按原步骤充分加热。'} for n in range(1,6)}
(ROOT/"ingredients.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
(ROOT/"recipes.json").write_text(json.dumps(recipes,ensure_ascii=False,indent=2),encoding="utf-8")
print(f"Wrote {len(catalog)} ingredients and {len(recipes)} unreviewed recipe drafts.")
