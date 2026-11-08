from decimal import Decimal
import pytest
from kitchen.store import Store, Conflict, now
from kitchen.domain import Inventory


def prepared(tmp_path,context):
    db=Store(tmp_path/"test.db")
    user,token=db.new_user()
    stock=db.save_inventory(user,context.inventory)
    db.save_preferences(user,context.preferences)
    run={"id":"run1","created_at":now(),"revision":1,"status":"ready","mode":"offline","preferences":context.preferences.model_dump(mode="json"),"plan":{"meals":[{"dishes":[{"recipe_id":"cabbage_egg","servings":1}]},{"dishes":[{"recipe_id":"pan_tofu","servings":1}]}]}}
    db.save_run(user,run)
    return db,user,token,stock


def test_idempotent_and_actual_usage(tmp_path,context):
    db,user,_,stock=prepared(tmp_path,context)
    first=db.confirm(user,"run1",0,1,stock.version,{"egg":1,"cabbage":80})
    second=db.confirm(user,"run1",0,1,stock.version,{"egg":1,"cabbage":80})
    assert not first["already_confirmed"] and second["already_confirmed"]
    remaining={x.ingredient_id:x.quantity for x in db.inventory(user).items}
    assert remaining["egg"]==2 and remaining["cabbage"]==120
    with pytest.raises(Conflict):db.confirm(user,"run1",0,1,stock.version,{"egg":2,"cabbage":80})


def test_stale_version_and_atomic_rejection(tmp_path,context):
    db,user,_,stock=prepared(tmp_path,context)
    with pytest.raises(Conflict):db.confirm(user,"run1",0,1,stock.version-1,{"egg":2,"cabbage":100})
    with pytest.raises(Conflict):db.confirm(user,"run1",0,1,stock.version,{"egg":4,"cabbage":100})
    assert db.inventory(user).version==stock.version
    assert db.inventory(user).items[0].quantity==3


def test_user_isolation_and_restart(tmp_path,context):
    db,user,token,_=prepared(tmp_path,context)
    other,_=db.new_user()
    assert db.inventory(other).items==[]
    with pytest.raises(KeyError):db.run(other,"run1")
    with pytest.raises(KeyError):db.confirm(other,"run1",0,1,0,{"egg":1,"cabbage":100})
    restarted=Store(tmp_path/"test.db")
    assert restarted.user_for_token(token)==user
    assert restarted.inventory(user).items[0].quantity==3


def test_review_is_per_user_and_not_cooking(tmp_path,context):
    db,user,_,_=prepared(tmp_path,context)
    other,_=db.new_user()
    db.review(user,"pan_tofu",True)
    assert next(r for r in db.recipes(user) if r.id=="pan_tofu").reviewed
    assert not next(r for r in db.recipes(other) if r.id=="pan_tofu").reviewed
    assert next(r for r in db.recipes(user) if r.id=="pan_tofu").cooked_count==0
