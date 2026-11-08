from __future__ import annotations

import hashlib
import json
import secrets
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from pathlib import Path

from .catalog import recipes, validate_inventory
from .domain import Inventory, Preferences, Recipe, Context, Plan, StockItem
from .planning import evaluate


def now():
    return datetime.now(timezone.utc).isoformat()


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, token_hash TEXT UNIQUE, inventory TEXT NOT NULL, preferences TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS confirmations(run_id TEXT NOT NULL, meal_index INTEGER NOT NULL, user_id TEXT NOT NULL, payload TEXT NOT NULL, UNIQUE(run_id, meal_index));
            CREATE TABLE IF NOT EXISTS reviews(user_id TEXT NOT NULL, recipe_id TEXT NOT NULL, reviewed_at TEXT NOT NULL, PRIMARY KEY(user_id, recipe_id));
            CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, run_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, payload TEXT NOT NULL, expires_at TEXT NOT NULL, receipt TEXT, fingerprint TEXT);
            CREATE TABLE IF NOT EXISTS request_keys(user_id TEXT NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL, run_id TEXT NOT NULL, PRIMARY KEY(user_id,key));
            CREATE TABLE IF NOT EXISTS model_attempts(id TEXT PRIMARY KEY, user_id TEXT NOT NULL, day TEXT NOT NULL, kind TEXT NOT NULL, created_at TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS attempts_day ON model_attempts(day,user_id);
            CREATE TABLE IF NOT EXISTS run_revisions(run_id TEXT NOT NULL,revision INTEGER NOT NULL,user_id TEXT NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(run_id,revision));
            """)
            if 'recipe_version' not in {r['name'] for r in db.execute('PRAGMA table_info(reviews)')}:
                db.execute('ALTER TABLE reviews ADD COLUMN recipe_version INTEGER NOT NULL DEFAULT 1')

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def new_user(self):
        token, user = secrets.token_urlsafe(32), secrets.token_hex(12)
        with self.db() as db:
            db.execute("INSERT INTO users VALUES (?,?,?,?,?)", (user, hashlib.sha256(token.encode()).hexdigest(), Inventory().model_dump_json(), Preferences().model_dump_json(), now()))
        return user, token

    def user_for_token(self, token):
        if not token:
            return None
        with self.db() as db:
            row = db.execute("SELECT id FROM users WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
            return row["id"] if row else None

    def inventory(self, user):
        with self.db() as db:
            return Inventory.model_validate_json(db.execute("SELECT inventory FROM users WHERE id=?", (user,)).fetchone()[0])

    def preferences(self, user):
        with self.db() as db:
            return Preferences.model_validate_json(db.execute("SELECT preferences FROM users WHERE id=?", (user,)).fetchone()[0])

    def save_preferences(self, user, prefs):
        with self.db() as db:
            old=db.execute('SELECT preferences FROM users WHERE id=?',(user,)).fetchone()
            db.execute("UPDATE users SET preferences=? WHERE id=?", (prefs.model_dump_json(), user))
            if old and json.loads(old[0])!=prefs.model_dump(mode='json'):
                self.invalidate_runs(db,user)

    def save_inventory(self, user, inventory):
        validate_inventory(inventory)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            current = Inventory.model_validate_json(db.execute("SELECT inventory FROM users WHERE id=?", (user,)).fetchone()[0])
            if inventory.version != current.version:
                raise Conflict("库存已更新，请刷新后重试")
            updated = inventory.model_copy(update={"version": current.version+1})
            db.execute("UPDATE users SET inventory=? WHERE id=?", (updated.model_dump_json(),user))
            self.invalidate_runs(db,user)
        return updated

    def recipes(self, user):
        with self.db() as db:
            reviews = {(x['recipe_id'],x['recipe_version']):x['reviewed_at'] for x in db.execute("SELECT * FROM reviews WHERE user_id=?", (user,))}
        return [r.model_copy(update={"reviewed": r.team_reviewed or (r.id,r.version) in reviews, "reviewed_at": r.team_reviewed_at if r.team_reviewed else reviews.get((r.id,r.version))}) for r in recipes()]

    def review(self, user, recipe_id, reviewed):
        if recipe_id not in {r.id for r in recipes()}:
            raise ValueError("不存在的菜谱")
        with self.db() as db:
            if reviewed:
                version=next(r.version for r in recipes() if r.id==recipe_id)
                db.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?,?)", (user,recipe_id,now(),version))
            else:
                db.execute("DELETE FROM reviews WHERE user_id=? AND recipe_id=?", (user,recipe_id))

    def context(self, user, prefs=None):
        return Context(inventory=self.inventory(user), preferences=prefs or self.preferences(user), recipes=self.recipes(user))

    def save_run(self, user, run):
        with self.db() as db:
            existing = db.execute("SELECT user_id FROM runs WHERE id=?", (run["id"],)).fetchone()
            if existing and existing[0] != user:
                raise ValueError("任务不存在")
            db.execute("INSERT INTO runs VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (run["id"],user,json.dumps(run,ensure_ascii=False),run["created_at"]))
            if run['status']!='running':
                db.execute('INSERT OR REPLACE INTO run_revisions VALUES (?,?,?,?)',(run['id'],run['revision'],user,json.dumps(run,ensure_ascii=False)))

    def run(self, user, run_id):
        with self.db() as db:
            row = db.execute("SELECT payload FROM runs WHERE user_id=? AND id=?", (user,run_id)).fetchone()
            if not row:
                raise KeyError("任务不存在")
            result = json.loads(row[0])
            result["confirmed_meals"] = [x[0] for x in db.execute("SELECT meal_index FROM confirmations WHERE user_id=? AND run_id=?", (user,run_id))]
            return result

    def list_runs(self, user):
        with self.db() as db:
            return [json.loads(x[0]) for x in db.execute("SELECT payload FROM runs WHERE user_id=? ORDER BY created_at DESC LIMIT 30", (user,))]

    def confirm(self, user, run_id, meal_index, revision, expected_version, actual):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM runs WHERE id=? AND user_id=?", (run_id,user)).fetchone()
            if not row:
                raise KeyError("任务不存在")
            run = json.loads(row[0])
            old = db.execute("SELECT payload FROM confirmations WHERE run_id=? AND meal_index=? AND user_id=?", (run_id,meal_index,user)).fetchone()
            normalized = {k:str(Decimal(str(v))) for k,v in actual.items()}
            if old:
                receipt = json.loads(old[0])
                if {k:Decimal(v) for k,v in receipt["actual"].items()} != {k:Decimal(v) for k,v in normalized.items()}:
                    raise Conflict("这一顿已确认，不能通过重复提交改写用量")
                return {"receipt":receipt,"already_confirmed":True}
            if run["status"] != "ready" or run["revision"] != revision:
                raise Conflict("计划已改变或尚未完成，请刷新")
            if meal_index < 0 or meal_index >= len(run["plan"]["meals"]):
                raise ValueError("餐次不存在")
            inventory = Inventory.model_validate_json(db.execute("SELECT inventory FROM users WHERE id=?",(user,)).fetchone()[0])
            if inventory.version != expected_version:
                raise Conflict("库存已变化，请刷新库存后再次确认实际用量")
            # Revalidate the selected meal against current inventory and current review status.
            context = self.context(user, Preferences.model_validate(run["preferences"]))
            context.inventory = inventory
            selected = Plan(meals=[run["plan"]["meals"][meal_index]])
            report = evaluate(selected, context, check_meal_count=False)
            blocking = [v for v in report["violations"] if v["code"] != "stock"]
            if blocking:
                raise Conflict("当前计划条件已失效，请重新规划")
            required_keys = set(report["consumption"])
            if not required_keys <= actual.keys():
                raise ValueError("请逐项确认计划食材的实际消耗，可明确填 0")
            stock = {x.ingredient_id:x for x in inventory.items}
            for key, value in normalized.items():
                amount = Decimal(value)
                if not amount.is_finite() or amount < 0 or key not in stock or amount > stock[key].quantity:
                    raise Conflict("实际用量无效或超过当前库存")
                if stock[key].unit == "piece" and amount != amount.to_integral_value():
                    raise ValueError("按个计量的食材须填写整数")
                stock[key].quantity -= amount
            inventory.version += 1
            validate_inventory(inventory)
            db.execute("UPDATE users SET inventory=? WHERE id=?", (inventory.model_dump_json(),user))
            receipt = {"run_id":run_id,"meal_index":meal_index,"actual":normalized,"confirmed_at":now(),"inventory_version":inventory.version}
            db.execute("INSERT INTO confirmations VALUES (?,?,?,?)", (run_id,meal_index,user,json.dumps(receipt,ensure_ascii=False)))
            self.invalidate_runs(db,user,except_id=run_id)
            confirmed={x[0] for x in db.execute('SELECT meal_index FROM confirmations WHERE run_id=?',(run_id,))}
            remaining_meals=[m for i,m in enumerate(run['plan']['meals']) if i not in confirmed]
            run['inventory_version']=inventory.version
            if remaining_meals:
                context.inventory=inventory
                remainder=evaluate(Plan(meals=remaining_meals),context,check_meal_count=False)
                if not remainder['feasible']:
                    run.update(status='needs_input',message='实际消耗后剩余餐次已不满足库存或限制，请根据剩余库存新建规划。')
                elif run.get('validation'):
                    run['validation']['remaining']=remainder['remaining']
            elif run.get('validation'):
                run['validation']['remaining']=[x.model_dump(mode='json') for x in inventory.items]
            db.execute('UPDATE runs SET payload=? WHERE id=?',(json.dumps(run,ensure_ascii=False),run_id))
            return {"receipt":receipt,"already_confirmed":False}

    def invalidate_runs(self, db, user, except_id=None):
        for row in db.execute('SELECT id,payload FROM runs WHERE user_id=?',(user,)).fetchall():
            run=json.loads(row['payload'])
            if row['id']!=except_id and run['status']=='ready':
                run.update(status='needs_input',message='库存或用餐条件已更新，这份计划需要重新核对；请按当前确认条件重新规划。')
                db.execute('UPDATE runs SET payload=? WHERE id=?',(json.dumps(run,ensure_ascii=False),row['id']))

    def create_proposal(self,user,kind,payload,inventory_version,preferences_snapshot):
        ident=secrets.token_hex(12)
        expires=(datetime.now(timezone.utc)+timedelta(minutes=30)).isoformat()
        data={**payload,'id':ident,'kind':kind,'inventory_version':inventory_version,'preferences_snapshot':preferences_snapshot.model_dump(mode='json'),'expires_at':expires}
        with self.db() as db:
            db.execute('INSERT INTO proposals VALUES (?,?,?,?,NULL,NULL)',(ident,user,json.dumps(data,ensure_ascii=False),expires))
        return data

    def confirm_proposal(self,user,ident,body):
        normalized=body.model_dump(mode='json')
        fingerprint=json.dumps(normalized,sort_keys=True,ensure_ascii=False)
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT * FROM proposals WHERE id=? AND user_id=?',(ident,user)).fetchone()
            if not row: raise KeyError('proposal')
            if row['receipt']:
                # Normalize defaults in receipts saved before new confirmation fields existed.
                from .proposals import ProposalConfirmation
                previous = json.dumps(ProposalConfirmation.model_validate_json(row['fingerprint']).model_dump(mode='json'),sort_keys=True,ensure_ascii=False)
                if previous!=fingerprint: raise Conflict('该确认已经提交，不能通过重复请求改变数量')
                return {**json.loads(row['receipt']),'already_confirmed':True}
            if row['expires_at']<now(): raise Conflict('观察结果已超过30分钟，请重新盘点或整理')
            data=json.loads(row['payload'])
            current=db.execute('SELECT inventory,preferences FROM users WHERE id=?',(user,)).fetchone()
            inventory=Inventory.model_validate_json(current['inventory'])
            if inventory.version!=body.inventory_version or inventory.version!=data['inventory_version']:
                raise Conflict('观察期间库存已变化，请刷新后重新核对')
            if body.preferences is not None and json.loads(current['preferences'])!=data['preferences_snapshot']:
                raise Conflict('偏好已发生变化，请重新整理并确认')
            if data.get('questions') and not body.questions_resolved:
                raise ValueError('请先确认所有待回答问题已处理')
            if data.get('source') == 'vision' or data.get('image_count', 0):
                if any(item.action != 'keep' and not item.identity_confirmed for item in body.changes):
                    raise ValueError('照片识别的食材种类须逐项核对确认后才能更新库存')
            by_id={x.ingredient_id:x for x in inventory.items}
            changed=False
            for item in body.changes:
                if item.action=='keep': continue
                amount=item.quantity
                if item.action=='add' and item.ingredient_id in by_id:
                    amount+=by_id[item.ingredient_id].quantity
                by_id[item.ingredient_id]=StockItem(ingredient_id=item.ingredient_id,quantity=amount,unit=item.unit)
                changed=True
            inventory.items=list(by_id.values())
            validate_inventory(inventory)
            if changed:
                inventory.version+=1
                db.execute('UPDATE users SET inventory=? WHERE id=?',(inventory.model_dump_json(),user))
            if body.preferences is not None:
                db.execute('UPDATE users SET preferences=? WHERE id=?',(body.preferences.model_dump_json(),user))
            if changed or body.preferences is not None: self.invalidate_runs(db,user)
            receipt={'inventory':inventory.model_dump(mode='json'),'preferences':body.preferences.model_dump(mode='json') if body.preferences else json.loads(current['preferences']),'already_confirmed':False}
            db.execute('UPDATE proposals SET receipt=?,fingerprint=? WHERE id=?',(json.dumps(receipt,ensure_ascii=False),fingerprint,ident))
            return receipt

    def record_model_attempt(self,user,kind):
        day=now()[:10]
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            total=db.execute('SELECT COUNT(*) FROM model_attempts WHERE day=?',(day,)).fetchone()[0]
            personal=db.execute('SELECT COUNT(*) FROM model_attempts WHERE day=? AND user_id=?',(day,user)).fetchone()[0]
            if total>=int(os.environ.get('KITCHEN_DAILY_GLOBAL_CALLS','100')) or personal>=int(os.environ.get('KITCHEN_DAILY_USER_CALLS','20')):
                raise PermissionError('当日模型请求额度已用完，已停止新增请求')
            db.execute('INSERT INTO model_attempts VALUES (?,?,?,?,?)',(secrets.token_hex(12),user,day,kind,now()))

    def recover_interrupted(self):
        with self.db() as db:
            for row in db.execute('SELECT id,payload FROM runs').fetchall():
                run=json.loads(row['payload'])
                if run['status']=='running':
                    run.update(status='error',message='服务重启导致任务中断，未自动重发模型请求。',error_type='Interrupted')
                    db.execute('UPDATE runs SET payload=? WHERE id=?',(json.dumps(run,ensure_ascii=False),row['id']))

    def request_run(self,user,key,fingerprint):
        with self.db() as db:
            row=db.execute('SELECT * FROM request_keys WHERE user_id=? AND key=?',(user,key)).fetchone()
        if not row: return None
        if row['fingerprint']!=fingerprint: raise Conflict('同一请求标识不能用于不同条件')
        return self.run(user,row['run_id'])

    def remember_request(self,user,key,fingerprint,run_id):
        with self.db() as db:
            db.execute('INSERT INTO request_keys VALUES (?,?,?,?)',(user,key,fingerprint,run_id))

    def save_feedback(self, user, run_id, payload):
        self.run(user,run_id)
        with self.db() as db:
            confirmation = db.execute("SELECT 1 FROM confirmations WHERE user_id=? AND run_id=? AND meal_index=?", (user,run_id,payload["meal_index"])).fetchone()
            if not confirmation:
                raise ValueError("请先确认这一顿的实际用量")
            db.execute("INSERT INTO feedback VALUES (?,?,?,?)", (secrets.token_hex(12),user,run_id,json.dumps({**payload,"created_at":now()},ensure_ascii=False)))
