"""Opt-in real SSH/Linux integration. Requires Docker and OpenSSH, no personal credentials.
Creates an isolated container and disposable key, removes both on completion.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent_pool.remote import RemoteClient


def run(argv, **kw):
    result = subprocess.run(argv, text=True, capture_output=True, **kw)
    if result.returncode:
        raise RuntimeError("Command failed: " + repr(argv) + "\n" + result.stdout[-6000:] + "\n" + result.stderr[-6000:])
    return result.stdout.strip()


def main():
    if os.name == 'nt':
        raise SystemExit('Run this opt-in fixture from macOS or Linux (Windows CLI covered separately).')
    name = 'agent-pool-ssh-' + uuid.uuid4().hex[:10]
    oldpath = os.environ.get('PATH', '')
    started = False
    with tempfile.TemporaryDirectory(prefix='agent-pool-ssh-') as tmp:
        stage = Path(tmp)
        shutil.copytree(ROOT/'agent_pool', stage/'agent_pool', ignore=shutil.ignore_patterns('__pycache__'))
        for path in (ROOT/'tests/ssh-fixture').iterdir():
            shutil.copy2(path, stage/path.name)
        key = stage/'key'
        run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)])
        shutil.copy2(key.with_suffix('.pub'), stage/'authorized_keys')
        try:
            print('Building isolated Linux SSH fixture …', flush=True)
            run(['docker','build','--progress=plain','-t',name,str(stage)])
            run(['docker','run','-d','--name',name,'-p','127.0.0.1::22',name])
            started = True
            port = json.loads(run(['docker','inspect',name]))[0]['NetworkSettings']['Ports']['22/tcp'][0]['HostPort']
            hostkey = run(['docker','exec',name,'cat','/etc/ssh/ssh_host_ed25519_key.pub']).split()
            known = stage/'known_hosts'
            known.write_text('[127.0.0.1]:'+port+' '+hostkey[0]+' '+hostkey[1]+'\n')
            config = stage/'ssh_config'
            config.write_text(f'Host pool-test\n HostName 127.0.0.1\n Port {port}\n User agent\n IdentityFile {key}\n IdentitiesOnly yes\n UserKnownHostsFile {known}\n StrictHostKeyChecking yes\n')
            shimdir = stage/'bin';shimdir.mkdir()
            import shlex
            ssh = shutil.which('ssh')
            shim = shimdir/'ssh'
            shim.write_text('#!/bin/sh\nexec '+shlex.quote(ssh)+' -F '+shlex.quote(str(config))+' "$@"\n')
            shim.chmod(0o700)
            os.environ['PATH'] = str(shimdir)+os.pathsep+oldpath
            def server(*args):
                return run(['docker','exec','-u','agent',name,'python3','-m','agent_pool',*args])
            server('init')
            server('workspace','add','demo','--path','/home/agent/work')
            server('profile','enable','codex-1')
            client = RemoteClient({'host':'pool-test','command':'/usr/local/bin/agent-pool','home':'/home/agent/.local/share/agent-pool'})
            deadline=time.monotonic()+15
            while True:
                try:
                    doctor=client.data(['doctor']);break
                except ValueError:
                    if time.monotonic()>deadline:raise
                    time.sleep(.3)
            assert any(c.get('version')=='codex-fixture 1.0' for c in doctor['checks'])
            prompt='Prüfe Linux 🧭 $(touch /tmp/pool-pwned)'
            argv=['job','submit','--provider','codex','--workspace','demo','--prompt',prompt,'--key','lost-ack']
            # Kill the actual SSH client after the commit but before the delayed response.
            proc=subprocess.Popen(client.command(),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            proc.stdin.write(json.dumps({'version':1,'argv':argv}).encode());proc.stdin.close()
            for _ in range(30):
                jobs=json.loads(server('job','list'))
                if jobs:break
                time.sleep(.1)
            assert jobs, 'Request never reached Linux'
            proc.kill();proc.wait(timeout=5)
            proc.stdout.close();proc.stderr.close()
            again=client.data(argv)
            assert again['id']==jobs[0]['id']
            assert len(client.data(['job','list']))==1
            # Launch worker independently of every SSH connection; it survives client disconnects.
            worker=run(['docker','exec','-d','-u','agent',name,'python3','-m','agent_pool','work','--poll','1'])
            result=client.data(['job','wait',again['id'],'--seconds','15'])
            assert result['status']=='succeeded', result
            assert result['result']=='Linux SSH fixture report: '+prompt
            assert run(['docker','exec',name,'cat','/home/agent/work/executions.txt'])=='executed'
            assert run(['docker','exec',name,'sh','-c','test ! -e /tmp/pool-pwned && echo literal'])=='literal'
            status=client.data(['status'])
            assert status['worker']['online']
            assert any(a.get('connected') for a in status['accounts'])
            # Queue cancellation remains usable while the persistent worker is running.
            server('profile','disable','codex-1')
            pending=client.data(['job','submit','--provider','codex','--workspace','demo','--prompt','waiting','--key','waiting-1'])
            cancelled=client.data(['job','cancel',pending['id']])
            assert cancelled['status']=='cancelled'
            # The public CLI uses the same remote over a restricted forced-command key.
            keyline = run(['docker','exec',name,'cat','/home/agent/.ssh/authorized_keys'])
            restricted = 'restrict,command="/usr/local/bin/agent-pool --home /home/agent/.local/share/agent-pool rpc" '+keyline+'\n'
            run(['docker','exec',name,'python3','-c','import sys;from pathlib import Path;Path(sys.argv[1]).write_text(sys.argv[2])','/home/agent/.ssh/authorized_keys',restricted])
            cli=[sys.executable,'-m','agent_pool','--home',str(stage/'client')]
            run([*cli,'remote','add','central','--host','pool-test','--command','/usr/local/bin/agent-pool','--server-home','/home/agent/.local/share/agent-pool'],cwd=ROOT)
            cli_result=json.loads(run([*cli,'--remote','central','job','get',again['id']],cwd=ROOT))
            assert cli_result['result']==result['result']
            rejected=client.request(['profile','add','bad','--provider','codex'])
            assert rejected['code']==1
            evidence={'platform':'Linux container / Python 3.12 / real OpenSSH','provider':'controlled fixture, no inference',
                'lost_ack_idempotent':True,'execution_count':1,'utf8_roundtrip':True,'literal_shell_payload':True,
                'independent_worker':True,'heartbeat_online':True,'administration_with_worker':True,
                'restricted_ssh_key':True,'public_cli_roundtrip':True}
            print(json.dumps(evidence,indent=2),flush=True)
            (ROOT/'docs/remote-ssh-validation.json').write_text(json.dumps(evidence,indent=2)+'\n')
        finally:
            os.environ['PATH']=oldpath
            if started:
                subprocess.run(['docker','rm','-f',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            subprocess.run(['docker','image','rm',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)


if __name__=='__main__':
    main()
