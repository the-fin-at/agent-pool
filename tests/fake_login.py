"""Native CLI fixture for device/browser login. Never contacts a provider."""
import json
import os
import sys
import time
from pathlib import Path

provider = 'codex' if os.environ.get('CODEX_HOME') else 'claude'
home = Path(os.environ.get('CODEX_HOME') or os.environ['CLAUDE_CONFIG_DIR'])
accepted = home/'fixture-accepted'
if sys.argv[1:] in (['login','status'],['auth','status']):
    if provider=='codex':
        if not accepted.exists():sys.exit(1)
        print('Logged in using ChatGPT')
    else:
        print(json.dumps({'loggedIn':accepted.exists(),'authMethod':'claude.ai' if accepted.exists() else 'none','email':'fixture@example.invalid','subscriptionType':'max','configDirectory':str(home)}))
        sys.exit(0 if accepted.exists() else 1)
elif 'app-server' in sys.argv:
    for line in sys.stdin:
        message=json.loads(line)
        if message['method']=='initialized':continue
        if message['method']=='account/read':
            result={'account':{'type':'chatgpt','email':'fixture@example.invalid','planType':'team'} if accepted.exists() else None}
        elif message['method']=='account/rateLimits/read':
            result={'rateLimits':{'primary':{'usedPercent':25,'windowDurationMins':300,'resetsAt':time.time()+600}}}
        else:result={}
        print(json.dumps({'id':message['id'],'result':result}),flush=True)
else:
    (home/'fixture-native.pid').write_text(str(os.getpid()))
    if provider=='codex':
        print('Open https://auth.openai.com/codex/device\nEnter this code: ABCD-EFGHI',flush=True)
        deadline=time.monotonic()+30
        while not accepted.exists() and time.monotonic()<deadline:time.sleep(.05)
        if not accepted.exists():sys.exit(1)
    else:
        print('Visit https://claude.com/oauth/authorize?state=fixture-only\nPaste code here if prompted > ',end='',flush=True)
        code=sys.stdin.readline().strip()
        if code!='fixture-authorized-code':sys.exit(1)
        accepted.write_text('fixture-only')
    print('Login successful',flush=True)
