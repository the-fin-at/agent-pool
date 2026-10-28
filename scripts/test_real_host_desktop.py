"""Opt-in native Mac/Tk user and performance checks against a configured real SSH host.
No provider consent is completed. Starts and cancels one native device login in codex-1.
"""
import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from agent_pool.desktop import Dashboard
from agent_pool.desktop_theme import register_fonts
from agent_pool.remote import RemoteClient,RemoteConfig,discover
from agent_pool.store import default_home
from agent_pool.monitor import account_view
import tkinter as tk

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--remote',required=True)
p.add_argument('--output',type=Path,required=True)
p.add_argument('--screenshot',type=Path)
args=p.parse_args()
config=RemoteConfig(default_home()).get(args.remote);client=RemoteClient(config)
report={'real_ssh':True,'real_server_metadata':True,'human_consent_completed':False,'checks':{}}
latencies=[]
for _ in range(20):
    start=time.monotonic();state=client.data(['status']);latencies.append((time.monotonic()-start)*1000)
assert state['worker']['online']
assert any(a['connected'] for a in state['accounts'])
p95=sorted(latencies)[18]
report['status_latency_ms']={'samples':20,'p50':round(statistics.median(latencies),2),'p95':round(p95,2),'max':round(max(latencies),2)}
assert p95<3000,report['status_latency_ms']
register_fonts()
with tempfile.TemporaryDirectory(prefix='fleet-real-gui-') as tmp:
    root=tk.Tk();errors=[];root.report_callback_exception=lambda *exc:errors.append(str(exc[1]))
    app=Dashboard(root,tmp,initial=[],refresh_fn=lambda home:[],start_refresh=False)
    app.auto.set(False)
    def settle(predicate,seconds=20):
        until=time.monotonic()+seconds
        while not predicate() and time.monotonic()<until:root.update();time.sleep(.005)
        assert predicate(),'GUI deadline: '+str(app.page)+' '+str(app.refresh_error)
    def pump(seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:root.update();time.sleep(.005)
    try:
        # Real user actions: context menu, discovery form, connected accounts, filters and details.
        app.scope_button.invoke();app.scope_options['remote'].invoke();root.update()
        app.add_button.invoke()
        app.connection_form['name'].set('Real host');app.connection_form['host'].set(config['host'])
        app.connect_button.invoke()
        settle(lambda:app.page=='accounts' and not app.refreshing)
        assert RemoteConfig(tmp).get('Real host')==config
        assert app.worker['online'];assert any(a['connected'] for a in app.accounts)
        app.provider_filter.set('codex');app.search.set('server-codex');root.update()
        assert app.rendered==['server-codex']
        account=next(a for a in app.accounts if a['name']=='server-codex')
        app.details(account_view(account));assert app.page=='details'
        app.go_back();app.search.set('');app.provider_filter.set('all');root.update()
        assert not any(isinstance(w,tk.Toplevel) for w in root.winfo_children())
        report['checks']['discovery_connection_filters_details_without_modals']=True
        # Real installed provider CLI supplies a device code; no code or login URL in artifacts.
        app.show_login({'name':'codex-1','provider':'codex'});app.login_start_button.invoke()
        settle(lambda:app.login_state is not None and app.login_state['state']=='awaiting_browser')
        ident=app.login_state['id'];assert app.login_state.get('device_code')
        app.go_back()
        settle(lambda:client.data(['auth','get',ident])['state']=='cancelled')
        report['checks']['real_ui_native_remote_login_and_abandon_cancel']=True
        # Failed actual SSH endpoint, then user recovery to the working server.
        RemoteConfig(tmp).add('Offline','fleet-nonexistent-test.invalid',config['command'],config['home'])
        app.select_remote('Offline');settle(lambda:not app.refreshing)
        assert app.refresh_error
        app.select_remote('Real host');settle(lambda:not app.refreshing)
        assert not app.refresh_error and any(a['connected'] for a in app.accounts)
        report['checks']['failed_ssh_recovery']=True
        # Inject slow transport only: actual UI/threading stays intact, and old replies cannot relabel a new target.
        intervals=[];previous=[time.monotonic()];running=[True]
        def pulse():
            now=time.monotonic();intervals.append((now-previous[0])*1000);previous[0]=now
            if running[0]:root.after(25,pulse)
        root.after(25,pulse)
        actual=RemoteClient.data
        def delayed(self,argv):time.sleep(2);return actual(self,argv)
        with patch.object(RemoteClient,'data',delayed):
            app.refresh();pump(.1);app.select_scope('local');settle(lambda:not app.refreshing);pump(2.7)
        assert app.scope=='local' and app.accounts==[]
        running[0]=False;root.update()
        report['event_loop_ms']={'samples':len(intervals),'p95':round(sorted(intervals)[int(len(intervals)*.95)-1],2),'max':round(max(intervals),2)}
        assert report['event_loop_ms']['p95']<100 and max(intervals)<500,report['event_loop_ms']
        report['checks']['delayed_transport_responsive_and_stale_reply_ignored']=True
        for _ in range(12):
            app.select_remote('Real host');app.select_scope('local')
        settle(lambda:not app.refreshing);pump(1)
        assert app.accounts==[] and not errors,errors
        report['checks']['rapid_context_switches_without_tk_errors']=True
        app.select_remote('Real host');settle(lambda:not app.refreshing)
        # Only server identities are redacted in the screenshot; quotas are the live read model.
        for a in app.accounts:a['email']=None
        app.render();pump(.5)
        if args.screenshot:
            assert sys.platform=='darwin','Screenshot helper is macOS-only'
            wake=subprocess.Popen(['caffeinate','-d','-u','-t','15'])
            try:
                pump(.7)
                swift='''import CoreGraphics;import Foundation
let p=Int(CommandLine.arguments[1])!
let ws=CGWindowListCopyWindowInfo([.optionOnScreenOnly,.excludeDesktopElements],kCGNullWindowID) as? [[String:Any]] ?? []
for w in ws where (w[kCGWindowOwnerPID as String] as? Int)==p && (w[kCGWindowLayer as String] as? Int)==0 {print(w[kCGWindowNumber as String]!);break}
'''
                helper=Path(tmp)/'capture.swift';helper.write_text(swift)
                wid=subprocess.check_output(['swift',str(helper),str(os.getpid())],text=True).strip()
                args.screenshot.parent.mkdir(parents=True,exist_ok=True)
                subprocess.run(['screencapture','-x','-o','-l',wid,str(args.screenshot)],check=True)
            finally:wake.terminate();wake.wait(timeout=5)
        assert not errors,errors
    finally:app.close()
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
