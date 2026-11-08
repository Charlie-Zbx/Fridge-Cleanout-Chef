"""Local container persistence check; default only checks Docker availability. No API keys."""
import argparse
import json
import secrets
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT=Path(__file__).resolve().parents[1]


def docker(*args,timeout=30):
    return subprocess.run(['docker',*args],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)


def require(*args,timeout=30):
    result=docker(*args,timeout=timeout)
    if result.returncode: raise RuntimeError('Docker '+args[0]+' failed: '+result.stderr[-1500:])
    return result.stdout.strip()


def wait_ready(client,seconds=45):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        try:
            response=client.get('/api/health')
            if response.status_code==200:
                assert response.json()['live_enabled'] is False
                return
        except httpx.TransportError:
            pass
        time.sleep(.5)
    raise TimeoutError('Container did not become healthy')


def verify(run=False,port=8012):
    try:
        result=docker('info','--format','{{.ServerVersion}}',timeout=10)
    except (OSError,subprocess.TimeoutExpired):
        return {'status':'blocked','reason':'Docker CLI or engine unavailable','model_calls':0}
    if result.returncode:
        return {'status':'blocked','reason':'Docker engine is not running','model_calls':0}
    if not run:
        return {'status':'ready_for_local_check','engine':result.stdout.strip(),'model_calls':0,'note':'Use --run to build a local image and verify isolated test data. No cloud service is created.'}
    name='yuwei-check-'+secrets.token_hex(5)
    image=name+':local';volume=name+'-data'
    output=ROOT/'artifacts'/name;output.mkdir(parents=True)
    report={'status':'running','model_calls':0,'port':port,'image':image,'volume':volume}
    volume_created=False;container_created=False
    try:
        build=docker('build','-t',image,'.',timeout=900)
        (output/'build.log').write_text(build.stdout+'\n'+build.stderr,encoding='utf-8')
        if build.returncode: raise RuntimeError('Image build failed; see local build.log')
        require('volume','create',volume);volume_created=True
        require('run','--detach','--name',name,'--publish',f'127.0.0.1:{port}:8000',
                '--mount',f'type=volume,source={volume},target=/var/data',
                '--env','KITCHEN_ENABLE_LIVE=0','--env','KITCHEN_ACCESS_CODE=local-test-code',image)
        container_created=True
        with httpx.Client(base_url=f'http://127.0.0.1:{port}',headers={'X-Kitchen-Client':'fridge-web'},timeout=4) as client:
            wait_ready(client)
            assert client.post('/api/session').status_code==401
            client.post('/api/session',json={'access_code':'local-test-code'}).raise_for_status()
            stock=client.put('/api/inventory',json={'version':0,'items':[{'ingredient_id':'egg','quantity':5,'unit':'piece'}],'pantry':['salt']})
            stock.raise_for_status();saved=stock.json()
            require('restart',name)
            wait_ready(client)
            assert client.get('/api/inventory').json()==saved
            with httpx.Client(base_url=str(client.base_url),headers={'X-Kitchen-Client':'fridge-web'},timeout=4) as other:
                other.post('/api/session',json={'access_code':'local-test-code'}).raise_for_status()
                assert other.get('/api/inventory').json()['items']==[]
        report.update(status='passed',checks=['build','health_live_disabled','access_code','inventory_persists_after_restart','new_browser_isolated'])
    except Exception as error:
        report.update(status='failed',error_type=type(error).__name__,reason=str(error))
    finally:
        # Remove only the random, task-owned resources created by this invocation.
        cleanup={}
        if container_created: cleanup['container']=docker('rm','--force',name).returncode==0
        if volume_created: cleanup['volume']=docker('volume','rm',volume).returncode==0
        report['cleanup']=cleanup
        report['note']='Built image retained locally; no production data or cloud service touched.'
        (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',action='store_true')
    parser.add_argument('--port',type=int,default=8012)
    args=parser.parse_args()
    if not 1024<=args.port<=65535: parser.error('port must be 1024–65535')
    result=verify(args.run,args.port)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    sys.exit(1 if result['status'] in ('failed','blocked') else 0)
