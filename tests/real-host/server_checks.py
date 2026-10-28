"""Runs only in a fresh, controlled pool on the explicitly selected real host."""
import concurrent.futures
import json
import os
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

archive=Path(sys.argv[1]).resolve();fixture=Path(sys.argv[2]).resolve()
report={'controlled_provider':True,'real_provider_inference':False,'checks':{},'performance':{}}
base=Path.home()/'.local/share/agent-fleet-validation';base.mkdir(parents=True,exist_ok=True,mode=0o700)

def command(home,*args,ok=(0,)):
    done=subprocess.run([sys.executable,str(archive),'--home',str(home),*map(str,args)],capture_output=True,text=True,timeout=45)
    assert done.returncode in ok,(args,done.returncode,done.stdout[-800:],done.stderr[-500:])
    return json.loads(done.stdout)

def poll(home,ident,states,seconds=20):
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        job=command(home,'job','get',ident,ok=(0,1,2))
        if job['status'] in states:return job
        time.sleep(.1)
    raise AssertionError(('Job deadline',ident,job['status']))

def worker(home):
    return subprocess.Popen([sys.executable,str(archive),'--home',str(home),'work','--poll','1'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

def stop(proc):
    if proc.poll() is None:proc.terminate()
    proc.wait(timeout=10)

with tempfile.TemporaryDirectory(prefix='loops-',dir=base) as tmp:
    root=Path(tmp);home=root/'pool';work=root/'workspace';work.mkdir()
    fixture.chmod(0o700)
    command(home,'profile','add','controlled','--provider','codex','--binary',fixture)
    command(home,'profile','enable','controlled')
    command(home,'workspace','add','test','--path',work)
    def submit(prompt,key):return command(home,'job','submit','--provider','codex','--workspace','test','--prompt',prompt,'--key',key,'--timeout','10')
    # Loop 2: same public RPC used by SSH clients, with malformed and shell-shaped inputs.
    bad=[{}, {'version':2,'argv':['status']},{'version':1,'argv':['work']},{'version':1,'argv':['profile','add','evil','--provider','codex']},{'version':1,'argv':['auth','input','a'*32,'--code-file','/etc/passwd']}]
    for request in bad:
        done=subprocess.run([sys.executable,str(archive),'--home',str(home),'rpc'],input=json.dumps(request),capture_output=True,text=True,timeout=10)
        assert json.loads(done.stdout)['code']==1,request
    report['checks']['malformed_rpc_rejected']=len(bad)
    payload='Prüfung 🧭 $(touch SHOULD-NOT-EXIST); `touch ALSO-NOT`; ${HOME}'
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        duplicate=list(pool.map(lambda _:submit(payload,'identical'),range(16)))
    assert len({j['id'] for j in duplicate})==1
    mismatch=command(home,'job','submit','--provider','codex','--workspace','test','--prompt','different','--key','identical',ok=(1,))
    assert 'Idempotency' in mismatch['error']
    report['checks']['concurrent_submissions_one_job']=16
    proc=worker(home)
    try:
        got=poll(home,duplicate[0]['id'],{'succeeded'})
        assert got['result']==payload
        assert not (work/'SHOULD-NOT-EXIST').exists() and not (work/'ALSO-NOT').exists()
        report['checks']['utf8_and_shell_payload_literal']=True
        # Explicit short and weekly observations; no sleep through a quota window.
        auth=home/'profiles/controlled'
        (auth/'quota.json').write_text(json.dumps({'primary':{'usedPercent':100,'windowDurationMins':300,'resetsAt':time.time()+3},'secondary':{'usedPercent':100,'windowDurationMins':10080,'resetsAt':time.time()+120}}))
        command(home,'quota','refresh','controlled')
        waiting=submit('after-quota','quota-wait')
        poll(home,waiting['id'],{'waiting'})
        time.sleep(3.2)
        current=command(home,'job','get',waiting['id'],ok=(2,))
        assert current['status']=='waiting' and current['attempts']==0
        report['checks']['weekly_limit_still_blocks_after_short_reset']=True
        (auth/'quota.json').unlink();command(home,'quota','refresh','controlled')
        assert poll(home,waiting['id'],{'succeeded'})['attempts']==1
        # Cancellation leaves a disabled-provider job untouched.
        command(home,'profile','disable','controlled')
        cancelled=submit('cancel-me','cancel')
        assert command(home,'job','cancel',cancelled['id'],ok=(0,))['status']=='cancelled'
        command(home,'profile','enable','controlled')
        report['checks']['queued_cancellation']=True
        # A killed job is never silently replayed on worker restart.
        (work/'native.pid').unlink(missing_ok=True)
        interrupted=submit('SLEEP:20','interruption')
        poll(home,interrupted['id'],{'running'})
        until=time.monotonic()+5
        while not (work/'native.pid').exists() and time.monotonic()<until:time.sleep(.05)
        pid=int((work/'native.pid').read_text());stop(proc)
        assert command(home,'job','get',interrupted['id'],ok=(1,))['status']=='needs_review'
        try:os.kill(pid,0)
        except ProcessLookupError:pass
        else:raise AssertionError('Native child survived controlled worker termination')
        proc=worker(home);time.sleep(.5)
        assert command(home,'job','get',interrupted['id'],ok=(1,))['status']=='needs_review'
        report['checks']['sigterm_child_cleanup_and_no_automatic_replay']=True
        # Loop 3: a bounded sustained queue, using native subprocesses for every job.
        start=time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            jobs=list(pool.map(lambda i:submit('LOAD:'+str(i),'load-'+str(i)),range(100)))
        for job in jobs:poll(home,job['id'],{'succeeded'},seconds=45)
        seconds=time.monotonic()-start
        executions=[json.loads(x) for x in (work/'executions.jsonl').read_text().splitlines()]
        load=[x for x in executions if x.startswith('LOAD:')]
        assert len(load)==100 and len(set(load))==100
        report['performance'].update(jobs=100,unique_executions=100,seconds=round(seconds,3),jobs_per_second=round(100/seconds,2))
        report['checks']['no_fixture_process_or_queue_leak']=True
    finally:stop(proc)
    # Login worker must work from the deployed extensionless archive and stop its native process.
    key='b'*32
    command(home,'auth','start','controlled','--provider','codex','--key',key)
    until=time.monotonic()+10
    while time.monotonic()<until:
        state=command(home,'auth','get',key)
        if state['state']=='awaiting_browser':break
        time.sleep(.1)
    assert state['state']=='awaiting_browser',state['state']
    pid=int((home/'profiles/controlled/native.pid').read_text())
    command(home,'auth','cancel',key)
    until=time.monotonic()+10
    while time.monotonic()<until:
        state=command(home,'auth','get',key)
        if state['state']=='cancelled':break
        time.sleep(.1)
    assert state['state']=='cancelled'
    try:os.kill(pid,0)
    except ProcessLookupError:pass
    else:raise AssertionError('Login child survived cancellation')
    report['checks']['installed_archive_login_and_native_cleanup']=True
print(json.dumps(report))
