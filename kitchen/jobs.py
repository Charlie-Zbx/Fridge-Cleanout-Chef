"""Single-process task runner. Durable status, no automatic paid retry on restart."""
import asyncio
import json
import os
import secrets
from contextlib import asynccontextmanager
from .catalog import validate_preferences
from .settings import require_live
from .store import Conflict, now


class Jobs:
    def __init__(self,store):
        self.store=store
        self.busy=set()
        self.tasks=set()

    def claim(self,user):
        if user in self.busy: raise Conflict('当前厨房已有任务正在执行，请等待完成')
        if len(self.busy)>=int(os.environ.get('KITCHEN_MAX_CONCURRENT','2')):
            raise Conflict('当前服务繁忙，请稍后再试；尚未调用模型')
        self.busy.add(user)

    @asynccontextmanager
    async def interactive(self,user):
        self.claim(user)
        try: yield
        finally: self.busy.discard(user)

    def start(self,body,user,existing=None):
        validate_preferences(body.preferences)
        if body.mode=='live': require_live(body.consent)
        fingerprint=json.dumps({'body':body.model_dump(mode='json'),'existing_id':existing['id'] if existing else None},sort_keys=True,ensure_ascii=False)
        found=self.store.request_run(user,body.request_id,fingerprint)
        if found: return found
        if existing and existing.get('confirmed_meals'): raise Conflict('已有餐次确认，请根据剩余库存创建新任务')
        if existing and existing['mode']!=body.mode: raise Conflict('切换模型模式请创建新任务')
        if existing and body.expected_revision!=existing['revision']: raise Conflict('计划版本已变化，请刷新')
        self.claim(user)
        try:
            self.store.save_preferences(user,body.preferences)
            ctx=self.store.context(user,body.preferences)
            run={'id':existing['id'] if existing else secrets.token_hex(12),'created_at':existing['created_at'] if existing else now(),'revision':existing['revision']+1 if existing else 1,'preferences':body.preferences.model_dump(mode='json'),'inventory_version':ctx.inventory.version,'status':'running','message':'正在发现工具并整理候选方案…','user_message':body.message,'plan':None,'mode':body.mode,'trace':[],'confirmed_meals':[],'model_calls':0,'usage':{}}
            self.store.save_run(user,run)
            self.store.remember_request(user,body.request_id,fingerprint,run['id'])
            task=asyncio.create_task(self.execute(body,user,ctx,run,existing))
            self.tasks.add(task);task.add_done_callback(self.tasks.discard)
            return run
        except BaseException:
            self.busy.discard(user)
            raise

    async def execute(self,body,user,ctx,run,existing):
        from .agent import run_agent
        def progress(trace):
            run['trace']=trace
            run['model_calls']=sum(e['kind']=='model' for e in trace)
            self.store.save_run(user,run)
        try:
            result=await run_agent(ctx,body.message,run['id'],mode=body.mode,consent=body.consent,checkpoint_path=self.store.path.parent/'checkpoints.db',previous={'message':existing['message'],'plan':existing.get('plan')} if existing else None,on_progress=progress,before_model=lambda:self.store.record_model_attempt(user,'planning'))
            run.update(result)
            if run['status']=='ready' and (self.store.inventory(user).version!=ctx.inventory.version or self.store.preferences(user)!=body.preferences):
                run.update(status='needs_input',message='规划期间库存或偏好已变化，请重新确认。',plan=None)
                run.pop('validation',None)
        except asyncio.CancelledError:
            run.update(status='error',message='任务已中断，未自动重试。',error_type='Interrupted',plan=None)
            raise
        except Exception as error:
            run.update(status='error',message='任务未完成，库存未扣减。',error_type=type(error).__name__,plan=None)
        finally:
            self.store.save_run(user,run)
            self.busy.discard(user)

    async def close(self):
        for task in list(self.tasks): task.cancel()
        if self.tasks: await asyncio.gather(*list(self.tasks),return_exceptions=True)
