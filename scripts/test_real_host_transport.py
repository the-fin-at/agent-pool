"""Opt-in real SSH lost-ack check, confined to a disposable pool on the selected host."""
import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent_pool.remote import RemoteClient,RemoteConfig
from agent_pool.store import default_home

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--remote',required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
config=RemoteConfig(default_home()).get(args.remote)
def shell(argv,input=None):
    done=subprocess.run(['ssh','-T','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ForwardAgent=no',config['host'],shlex.join(argv)],input=input,text=True,capture_output=True,timeout=20)
    if done.returncode:raise RuntimeError(done.stderr[-800:])
    return done.stdout.strip()
folder=shell(['mktemp','-d',config['home']+'/../agent-fleet-validation/transport.XXXXXX'])
child=None
try:
    pool=folder+'/pool';workspace=folder+'/work';wrapper=folder+'/delayed-rpc'
    shell(['python3','-c','import pathlib,sys;pathlib.Path(sys.argv[1]).mkdir()',workspace])
    shell([config['command'],'--home',pool,'workspace','add','test','--path',workspace])
    source='''#!/usr/bin/env python3
import subprocess,sys,time
r=subprocess.run([COMMAND,*sys.argv[1:]],input=sys.stdin.buffer.read(),capture_output=True)
time.sleep(3)
sys.stdout.buffer.write(r.stdout);sys.stderr.buffer.write(r.stderr)
sys.exit(r.returncode)
'''.replace('COMMAND',repr(config['command']))
    shell(['python3','-c','import pathlib,sys;p=pathlib.Path(sys.argv[1]);p.write_text(sys.stdin.read());p.chmod(0o700)',wrapper],source)
    direct=RemoteClient({**config,'home':pool})
    delayed=RemoteClient({**config,'home':pool,'command':wrapper})
    argv=['job','submit','--provider','codex','--workspace','test','--prompt','Lost ACK literal 🧭 $(touch SHOULD-NOT-EXIST)','--key','same-after-disconnect']
    child=subprocess.Popen(delayed.command(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    child.stdin.write(json.dumps({'version':1,'argv':argv}).encode());child.stdin.close();child.stdin=None
    until=time.monotonic()+10;jobs=[]
    while time.monotonic()<until:
        jobs=direct.data(['job','list'])
        if jobs:break
        time.sleep(.1)
    assert jobs and child.poll() is None,'Did not interrupt the reply between commit and delivery'
    child.kill();child.communicate(timeout=5)
    retry=direct.data(argv)
    assert retry['id']==jobs[0]['id'] and len(direct.data(['job','list']))==1
    assert direct.data(['job','cancel',retry['id']])['status']=='cancelled'
    report={'real_ssh':True,'controlled_pool':True,'provider_inference':False,'reply_interrupted_after_commit':True,'identical_retry_one_job':True,'no_model_worker_started':True}
    args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
finally:
    if child and child.poll() is None:child.kill();child.communicate(timeout=5)
    # The delayed response helper finishes after three seconds and never starts an executor.
    time.sleep(3.2)
    shell(['python3','-c','import pathlib,shutil,sys;p=pathlib.Path(sys.argv[1]);assert p.parent.name=="agent-fleet-validation" and p.name.startswith("transport.");shutil.rmtree(p)',folder])
