"""Run real Tauri/WKWebView acceptance against an isolated legacy database (macOS).

Requires built debug desktop with custom-protocol and the native CLI example.
No Tk, browser demo, network, provider account, or production state is used.
"""
import argparse
from contextlib import closing
import json
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from agent_pool.store import Store

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--desktop', type=Path, default=ROOT/'target/debug/agent-fleet-desktop')
args = parser.parse_args()
if sys.platform != 'darwin':
    parser.error('This harness currently validates the real macOS WKWebView; no Windows proof is implied.')
fixture = ROOT/'target/debug/examples/controlled_provider'
for path in [args.desktop, fixture]:
    if not path.is_file():
        parser.error('Build first: '+str(path))
if b'AGENT_FLEET_TEST_SCRIPT' not in args.desktop.read_bytes():
    parser.error('This harness requires the debug-only native hook; a release binary cannot report checks.')
args.output.mkdir(parents=True, exist_ok=True)
preflight = subprocess.run(['/usr/bin/swift', str(ROOT/'scripts/macos_gui_state.swift')], capture_output=True, text=True, timeout=15)
if preflight.returncode:
    parser.exit(77, 'Native GUI acceptance unavailable: macOS session state could not be read.\n')
session = json.loads(preflight.stdout)
if session['screen_locked'] or not session['console_session']:
    (args.output/'native-unavailable.json').write_text(json.dumps({'passed':False,'unavailable':'macOS session locked or not on console',**session},indent=2)+'\n')
    parser.exit(77, 'Native GUI acceptance unavailable: unlock the Mac and run from its console session. No app or provider was started.\n')
script = ROOT/'tests/native_desktop.js'
with tempfile.TemporaryDirectory(prefix='fleet-tauri-native-') as tmp:
    root = Path(tmp)
    home = root/'pool'
    native = root/'provider'
    shutil.copy2(fixture, native)
    user = root/'user'
    default_claude = user/'.claude'
    default_claude.mkdir(parents=True)
    (default_claude/'fixture-accepted').write_text('controlled native default')
    (default_claude/'fixture-default-only').write_text('requires unset config override')
    (default_claude/'fixture-email').write_text('native-default@example.invalid')
    binaries = root/'bin'
    binaries.mkdir()
    shutil.copy2(fixture, binaries/'claude')
    with closing(Store(home)) as store:
        for name, provider, used in [('privat', 'codex', 28), ('arbeit', 'codex', 8), ('team', 'claude', 82)]:
            store.add_profile(name, provider, str(native))
            store.update_profile(name, enabled=True, checked_at=time.time())
            (store.authdir(name)/'fixture-accepted').write_text('fixture-only')
            windows = [{'key':'five_hour', 'bucket':provider, 'minutes':300, 'used':used, 'reset':time.time()+1200, 'model':None},
                       {'key':'seven_day', 'bucket':provider, 'minutes':10080, 'used':42, 'reset':time.time()+3600, 'model':None}]
            store.set_windows(name, windows)
            store.cache_monitor(name, {'connected':True, 'email':name+'@example.invalid', 'plan':'team', 'windows':windows, 'observed_at':time.time(), 'checked_at':time.time()})
        for name, provider in [('login-codex', 'codex'), ('login-claude', 'claude')]:
            store.add_profile(name, provider, str(native))
        store.add_workspace('fixture', root)
        job = store.submit('Existing native acceptance report', root, 'codex', key='native-desktop')
        store.update_job(job['id'], status='succeeded', result='Preserved report from legacy database', chosen_profile='privat')
        ids_before = [j['id'] for j in store.jobs()]
    report = args.output/'native-report.json'
    report.unlink(missing_ok=True)
    env = os.environ.copy()
    env.update(AGENT_FLEET_TEST_SCRIPT=str(script), AGENT_FLEET_TEST_REPORT=str(report))
    # A missing default provider must be harmless, and must never reach a real login.
    env['PATH'] = str(binaries)+':/usr/bin:/bin:/usr/sbin:/sbin'
    env['CODEX_HOME'] = str(root/'absent-default-monitor-source')
    env['HOME'] = str(root/'user')
    env['USERPROFILE'] = env['HOME']
    env.pop('CLAUDE_CONFIG_DIR', None)
    with (args.output/'native-app.log').open('w') as log:
        app = subprocess.Popen([str(args.desktop.resolve()), '--home', str(home)], env=env, stdout=log, stderr=subprocess.STDOUT)
        (args.output/'native-process.json').write_text(json.dumps({'pid':app.pid,'binary':str(args.desktop.resolve()),'binary_sha256':hashlib.sha256(args.desktop.read_bytes()).hexdigest(),'mode':'debug-custom-protocol'},indent=2)+'\n')
        awake = subprocess.Popen(['/usr/bin/caffeinate','-d','-i','-w',str(app.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        until = time.monotonic()+90
        captured = False
        try:
            while app.poll() is None and time.monotonic() < until:
                if not captured and time.monotonic() > until-80:
                    # CoreGraphics window lookup; this captures the actual native window.
                    swift = root/'window.swift'
                    swift.write_text('import CoreGraphics\nlet pid = Int(CommandLine.arguments[1])!\nlet rows = CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements], kCGNullWindowID) as! [[String:Any]]\nfor r in rows { if r[kCGWindowOwnerPID as String] as? Int == pid && r[kCGWindowLayer as String] as? Int == 0 { print(r[kCGWindowNumber as String]!); break } }\n')
                    found = subprocess.run(['/usr/bin/swift', str(swift), str(app.pid)], capture_output=True, text=True, timeout=20)
                    if found.stdout.strip().isdigit():
                        capture = subprocess.run(['/usr/sbin/screencapture','-x','-o','-l',found.stdout.strip(),str(args.output/'native-overview.png')], capture_output=True)
                        captured = capture.returncode == 0
                time.sleep(.2)
            if app.poll() is None:
                raise RuntimeError('Native WebView acceptance timed out')
            if not report.is_file():
                raise RuntimeError('Native app exited without a WebView report; see native-app.log')
            result = json.loads(report.read_text())
            if app.returncode != 0 or not result.get('passed'):
                raise RuntimeError(json.dumps(result, ensure_ascii=False))
            with closing(Store(home)) as store:
                assert [j['id'] for j in store.jobs()] == ids_before, 'Desktop changed the job queue'
                assert store.job(ids_before[0])['result'] == 'Preserved report from legacy database'
                defaults = [p for p in store.profiles() if p.get('auth_mode') == 'native_default']
                assert len(defaults) == 1
                assert not (home/'profiles'/defaults[0]['name']).exists()
            assert (default_claude/'fixture-accepted').read_text() == 'controlled native default'
            assert not (default_claude/'fixture-parent.pid').exists()
            if not captured:
                raise RuntimeError('Native checks passed but no actual window screenshot was captured')
            until = time.monotonic()+4
            native_pids = []
            for path in (home/'profiles').rglob('fixture-parent.pid'):
                native_pids.append(int(path.read_text()))
            for pid in native_pids:
                while time.monotonic() < until:
                    state = subprocess.run(['ps','-p',str(pid),'-o','stat='],capture_output=True,text=True).stdout.strip()
                    if not state or state.startswith('Z'): break
                    time.sleep(.1)
                else: raise RuntimeError('A controlled native login child survived: '+str(pid))
            result['native_login_children_terminated'] = len(native_pids)
            result['database_preserved'] = True
            result['native_screenshot'] = captured
            report.write_text(json.dumps(result, indent=2, ensure_ascii=False)+'\n')
            print(report)
        finally:
            awake.terminate()
            awake.wait(timeout=5)
            for session_file in (home/'login-sessions').glob('*.json'):
                subprocess.run([str(ROOT/'target/debug/agent-fleet'),'--home',str(home),'auth','cancel',session_file.stem],capture_output=True,timeout=10)
            if app.poll() is None:
                app.terminate()
                try: app.wait(timeout=5)
                except subprocess.TimeoutExpired: app.kill(); app.wait()
