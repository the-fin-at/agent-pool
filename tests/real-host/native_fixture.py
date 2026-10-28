#!/usr/bin/env python3
"""Opt-in real-host controlled provider. Never uses credentials or contacts providers."""
import json
import os
import sys
import time
from pathlib import Path
home=Path(os.environ.get('CODEX_HOME',os.environ.get('CLAUDE_CONFIG_DIR','/tmp')))
if '--version' in sys.argv:
    print('controlled-real-host 1');sys.exit()
if 'app-server' in sys.argv:
    for line in sys.stdin:
        msg=json.loads(line)
        if msg['method']=='initialized':continue
        if msg['method']=='account/read':result={'account':{'type':'chatgpt','email':'controlled@example.invalid','planType':'team'}}
        elif msg['method']=='account/rateLimits/read':
            custom=home/'quota.json'
            result={'rateLimits':json.loads(custom.read_text()) if custom.exists() else {'primary':{'usedPercent':20,'windowDurationMins':300,'resetsAt':time.time()+600},'secondary':{'usedPercent':10,'windowDurationMins':10080,'resetsAt':time.time()+3600}}}
        else:result={}
        print(json.dumps({'id':msg['id'],'result':result}),flush=True)
    sys.exit()
if sys.argv[1:]==['login','status']:
    print('Logged in using ChatGPT');sys.exit()
if sys.argv[1:]==['login','--device-auth']:
    (home/'native.pid').write_text(str(os.getpid()))
    print('https://auth.openai.com/codex/device\nABCD-EFGHI',flush=True)
    time.sleep(120);sys.exit(1)
prompt=sys.stdin.read()
with open('executions.jsonl','a') as stream:stream.write(json.dumps(prompt)+'\n')
Path('native.pid').write_text(str(os.getpid()))
if prompt.startswith('SLEEP:'):time.sleep(float(prompt.split(':',1)[1]))
print(json.dumps({'type':'item.completed','item':{'type':'agent_message','text':prompt}}))
print(json.dumps({'type':'turn.completed'}))
