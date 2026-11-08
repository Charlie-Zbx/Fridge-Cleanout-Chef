from __future__ import annotations

import asyncio
import os
import secrets
import time
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, Request, Response, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import Field, ValidationError

from .catalog import ingredients, PANTRY, EQUIPMENT, ALLERGENS, validate_inventory, validate_preferences
from .domain import Model, Inventory, Preferences
from .settings import ROOT, data_dir, live_available, require_live
from .store import Store, Conflict, now
from .jobs import Jobs
from .proposals import ProposalConfirmation, interpret


class RunRequest(Model):
    message: str = Field(default="请根据已确认库存安排接下来的饭菜。",min_length=1,max_length=3000)
    preferences: Preferences
    mode: Literal["offline","live"] = "offline"
    consent: bool = False
    request_id: str = Field(default_factory=lambda:secrets.token_hex(16),min_length=8,max_length=100)
    expected_revision: int | None = Field(default=None,ge=1)


class IntakeRequest(Model):
    preferences: Preferences | None = None
    message: str = Field(min_length=1,max_length=3000)
    mode: Literal['offline','live'] = 'offline'
    consent: bool = False


class SessionRequest(Model):
    access_code: str = Field(default='',max_length=200)


class Confirmation(Model):
    meal_index: int = Field(ge=0,le=1)
    revision: int = Field(ge=1)
    inventory_version: int = Field(ge=0)
    actual: dict[str,Decimal]


class ReviewRequest(Model):
    reviewed: bool


class Feedback(Model):
    meal_index: int = Field(ge=0,le=1)
    rating: int = Field(ge=1,le=5)
    actual_minutes: int = Field(ge=1,le=300)
    comment: str = Field(default="",max_length=1000)


def create_app(database: Path | None = None):
    store = Store(database or data_dir()/"kitchen.db")
    jobs=Jobs(store)
    @asynccontextmanager
    async def lifespan(app):
        if os.environ.get('KITCHEN_PUBLIC')=='1' and (not os.environ.get('KITCHEN_ACCESS_CODE') or os.environ.get('KITCHEN_SECURE_COOKIE')!='1'):
            raise RuntimeError('公开部署必须设置访问码并启用 Secure Cookie')
        store.recover_interrupted()
        yield
        await jobs.close()
    app = FastAPI(title="冰箱清库存厨师",version="0.2.0",lifespan=lifespan)
    app.state.store = store
    app.state.jobs = jobs
    access_attempts={}


    @app.middleware("http")
    async def boundary(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            if request.method not in ("GET","HEAD","OPTIONS"):
                origin = request.headers.get("origin")
                if origin and urlsplit(origin).netloc != request.headers.get("host"):
                    return JSONResponse({"detail":"不接受跨站修改请求"},status_code=403)
                if request.headers.get("x-kitchen-client") != "fridge-web":
                    return JSONResponse({"detail":"缺少客户端请求标识"},status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Conflict)
    async def conflict_handler(request, error):
        return JSONResponse({"detail":str(error)},status_code=409)

    @app.exception_handler(ValueError)
    async def value_handler(request, error):
        return JSONResponse({"detail":str(error)},status_code=422)

    @app.exception_handler(KeyError)
    async def missing_handler(request, error):
        return JSONResponse({"detail":"任务不存在"},status_code=404)

    @app.exception_handler(PermissionError)
    async def permission_handler(request, error):
        return JSONResponse({"detail":str(error)},status_code=403)

    def user(request: Request):
        identity = store.user_for_token(request.cookies.get("kitchen_session"))
        if not identity:
            raise HTTPException(401,"请刷新页面建立本地会话")
        return identity

    @app.get("/api/health")
    def health():
        return {"status":"ok","live_enabled":live_available(),"version":"0.2.0"}

    @app.post("/api/session")
    def session(request: Request,response: Response,body: SessionRequest | None=None):
        identity = store.user_for_token(request.cookies.get("kitchen_session"))
        if not identity:
            required=os.environ.get('KITCHEN_ACCESS_CODE','')
            if required:
                address=request.client.host if request.client else 'unknown'
                timestamp=time.monotonic()
                hits=[t for t in access_attempts.get(address,[]) if t>timestamp-60]
                access_attempts[address]=hits
                if len(hits)>=5: raise HTTPException(429,'请稍后再尝试访问码')
                if not secrets.compare_digest((body.access_code if body else '').encode(),required.encode()):
                    hits.append(timestamp)
                    raise HTTPException(401,'请输入试用访问码')
            identity,token = store.new_user()
            response.set_cookie("kitchen_session",token,httponly=True,samesite="strict",secure=os.environ.get("KITCHEN_SECURE_COOKIE")=="1",max_age=60*60*24*30)
        return {"user_label":"厨房 "+identity[:6],"live_enabled":live_available(),"api_key_present":bool(os.environ.get("DEEPSEEK_API_KEY")),"inventory":store.inventory(identity).model_dump(mode="json"),"preferences":store.preferences(identity).model_dump(mode="json")}

    @app.get("/api/catalog")
    def catalog(identity=Depends(user)):
        return {"ingredients":[v.model_dump() for v in ingredients().values()],"pantry":PANTRY,"equipment":EQUIPMENT,"allergens":ALLERGENS,"recipes":[r.model_dump(mode="json") for r in store.recipes(identity)]}

    @app.get("/api/inventory")
    def get_inventory(identity=Depends(user)):
        return store.inventory(identity)

    @app.put("/api/inventory")
    def put_inventory(body: Inventory,identity=Depends(user)):
        return store.save_inventory(identity,body)

    @app.post("/api/recipes/{recipe_id}/review")
    def review(recipe_id: str,body: ReviewRequest,identity=Depends(user)):
        store.review(identity,recipe_id,body.reviewed)
        return {"ok":True,"reviewed":body.reviewed,"cooked_verified":False}

    @app.post('/api/runs',status_code=202)
    async def create_run(body: RunRequest, identity=Depends(user)):
        return jobs.start(body,identity)

    @app.get("/api/runs")
    def history(identity=Depends(user)):
        return store.list_runs(identity)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str,identity=Depends(user)):
        return store.run(identity,run_id)

    @app.post("/api/runs/{run_id}/reply",status_code=202)
    async def reply(run_id: str,body: RunRequest,identity=Depends(user)):
        return jobs.start(body,identity,store.run(identity,run_id))

    @app.post("/api/runs/{run_id}/confirm")
    def confirm(run_id: str,body: Confirmation,identity=Depends(user)):
        result = store.confirm(identity,run_id,body.meal_index,body.revision,body.inventory_version,body.actual)
        return {**result,"inventory":store.inventory(identity).model_dump(mode="json")}

    @app.post("/api/runs/{run_id}/feedback")
    def feedback(run_id: str,body: Feedback,identity=Depends(user)):
        store.save_feedback(identity,run_id,body.model_dump())
        return {"ok":True}

    @app.post('/api/intake')
    async def intake(body: IntakeRequest,identity=Depends(user)):
        if body.mode=='live': require_live(body.consent)
        snapshot=store.inventory(identity)
        prefs=store.preferences(identity)
        async with jobs.interactive(identity):
            try:
                async with asyncio.timeout(40):
                    result=await interpret(body.message,body.preferences or prefs,snapshot,mode=body.mode,consent=body.consent,before_model=lambda:store.record_model_attempt(identity,'intake'))
            except (PermissionError,ValueError): raise
            except Exception as error:
                raise HTTPException(502,'需求整理未完成，未修改库存或偏好。') from error
        return store.create_proposal(identity,'intake',result,snapshot.version,prefs)

    @app.post('/api/proposals/{proposal_id}/confirm')
    def confirm_proposal(proposal_id: str,body: ProposalConfirmation,identity=Depends(user)):
        return store.confirm_proposal(identity,proposal_id,body)

    @app.post('/api/stocktakes')
    def manual_stocktake(identity=Depends(user)):
        stock=store.inventory(identity)
        return store.create_proposal(identity,'stocktake',{'items':[{'ingredient_id':x.ingredient_id,'name':ingredients()[x.ingredient_id].name,'unit':x.unit,'suggested_quantity':str(x.quantity),'basis':'账面数量，请手动核对'} for x in stock.items],'questions':[],'note':'手动盘点，不调用模型。'},stock.version,store.preferences(identity))

    @app.post('/api/vision')
    async def vision(files: list[UploadFile] | None=File(None),file: UploadFile | None=File(None),consent: bool=Form(False),purpose: Literal['add','stocktake']=Form('stocktake'),identity=Depends(user)):
        require_live(consent)
        uploads=files or ([file] if file else [])
        if not 1<=len(uploads)<=3: raise ValueError('每次请选择1–3张照片')
        snapshot=store.inventory(identity)
        prefs=store.preferences(identity)
        raw=[]
        try:
            for upload in uploads: raw.append(await upload.read(8*1024*1024+1))
        finally:
            for upload in uploads: await upload.close()
        from .vision import identify
        async with jobs.interactive(identity):
            try:
                result=await identify(raw,consent,before_model=lambda:store.record_model_attempt(identity,'vision'))
            except (ValueError,PermissionError): raise
            except Exception as error:
                raise HTTPException(502,'图片识别未完成，未修改库存。请检查模型权限或稍后重试。') from error
        return store.create_proposal(identity,purpose,{**result,'source':'vision'},snapshot.version,prefs)

    dist = ROOT/"frontend"/"dist"
    if dist.exists():
        app.mount("/assets",StaticFiles(directory=dist/"assets"),name="assets")
        @app.get("/{path:path}")
        def frontend(path: str):
            if path.startswith("api/"):
                raise HTTPException(404,"接口不存在")
            target = (dist/path).resolve()
            if target.is_relative_to(dist.resolve()) and target.is_file():
                return FileResponse(target)
            return FileResponse(dist/"index.html")
    else:
        @app.get("/")
        def unbuilt():
            return {"message":"后端已启动。请构建 frontend，或使用 Vite 开发服务器。","docs":"/docs","live_enabled":live_available()}
    return app


app = create_app()
