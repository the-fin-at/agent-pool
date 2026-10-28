"""Integrated native overview, connections and account sign-in; no task composer or modal prompts."""
import json
import re
import threading
import time
import uuid
import tkinter as tk
from tkinter import ttk
import webbrowser

from .desktop_theme import BG, SURFACE, INK, MUTED, LINE, ACCENT, GREEN, WARNING, SOFT
from .remote import RemoteClient, RemoteConfig, discover
from .providers import redact
from .login_sessions import ACTIVE, safe_url


class OverviewPanels:
    def toggle_scope_menu(self):
        if self.scope_menu is not None:
            self.close_scope_menu()
            return
        menu = self.scope_menu = ttk.Frame(self.root, style='Popover.TFrame')
        self.scope_options = {}
        for value, label, caption, icon in [('local','Lokal','Accounts auf diesem Rechner','laptop'), ('remote','Remote','Verbindungen und entfernte Accounts','globe2')]:
            row = ttk.Frame(menu,style='SelectedMenuRow.TFrame' if self.scope==value else 'MenuRow.TFrame')
            row.pack(fill='x',padx=2,pady=3)
            button = ttk.Button(row, text=label,
                image=self.theme.icon(icon), compound='left', style='ScopeOption.TButton', command=lambda v=value: self.select_scope(v))
            button.pack(fill='x')
            caption_label=self.text(row,caption,size=12,color=MUTED,bg=SOFT if self.scope==value else SURFACE)
            caption_label.pack(fill='x',padx=17,pady=(0,8))
            caption_label.bind('<Button-1>',lambda e,v=value:self.select_scope(v))
            self.scope_options[value] = button
            if self.scope == value:
                button.state(['selected'])
        x = self.scope_button.winfo_rootx()-self.root.winfo_rootx()
        y = self.scope_button.winfo_rooty()-self.root.winfo_rooty()+self.scope_button.winfo_height()+8
        menu.place(x=max(8,x), y=y, width=324)
        menu.lift()
        self.scope_options[self.scope].focus_set()

    def close_scope_menu(self):
        if self.scope_menu is not None:
            self.scope_menu.destroy()
            self.scope_menu = None
            self.scope_button.focus_set()

    def _outside_scope_menu(self, event):
        if self.scope_menu is None or event.widget == self.scope_button:
            return
        widget = event.widget
        while widget is not None:
            if widget == self.scope_menu:
                return
            widget = getattr(widget, 'master', None)
        self.close_scope_menu()

    def select_scope(self, value):
        self.leave_login()
        if value not in {'local','remote'}:
            return
        self.close_scope_menu()
        self.scope = value
        self.scope_button.configure(text='Lokal' if value == 'local' else 'Remote')
        self.scope_hint.configure(text='Auf diesem Rechner' if value == 'local' else 'Verbundene Rechner')
        self.provider_filter.set('all')
        self.search.set('')
        if value == 'local':
            self.target.set('Lokal')
            self._select_target()
        else:
            self.target_epoch += 1
            self.remote = None
            self.refreshing = False
            self.refresh_button.configure(state='normal', text='')
            self.refresh_error = None
            self.last_refresh = None
            self.accounts = []
            self.worker = None
            self.page = 'connections'
            self.render_connection_nav()
            self.render()
            self.probe_connections()

    def render_connection_nav(self):
        for child in self.connection_nav.winfo_children():
            child.destroy()
        if self.scope != 'remote':
            return
        self.text(self.connection_nav, 'Verbindungen', size=12, color=MUTED, bg=SURFACE).pack(anchor='w', padx=12, pady=(0,8))
        ttk.Button(self.connection_nav, text='Alle Verbindungen', style='Soft.TButton', command=lambda: self.select_scope('remote')).pack(fill='x', pady=(0,6))
        try:
            connections = RemoteConfig(self.home).all()
        except (ValueError, OSError):
            connections = {}
        for name in connections:
            button = ttk.Button(self.connection_nav, text=name, style='Soft.TButton', command=lambda n=name: self.select_remote(n))
            button.pack(fill='x', pady=3)

    def select_remote(self, name):
        self.target.set(name)
        self._select_target()

    def sync_header(self):
        account_page = self.page == 'accounts'
        if account_page:
            self.toolbar.pack(fill='x', padx=32, pady=(0,18), before=self.content)
            from .desktop_ui import PROVIDERS
            self.page_title.configure(text=PROVIDERS[self.provider_filter.get()], wraplength=0)
        else:
            self.toolbar.pack_forget()
        if (self.scope == 'remote' and self.page == 'accounts') or self.page in {'connect','login','details'}:
            self.breadcrumb.pack(fill='x', before=self.page_title.master, pady=(0,12))
            label = 'Verbindungen' if self.scope == 'remote' and self.page == 'accounts' else 'Zurück'
            self.back_button.configure(text=' '+label)
        else:
            self.breadcrumb.pack_forget()
        if self.scope=='remote':
            self.worker_text.configure(text=self.remote or 'Remote-Verbindungen',fg=MUTED)
        else:
            self.worker_text.configure(text='Auf diesem Rechner',fg=MUTED)
        self.add_button.configure(text='Verbindung hinzufügen' if self.page == 'connections' else 'Account hinzufügen')
        if self.page in {'connect','login','details'}:
            self.add_button.pack_forget()
            self.refresh_button.pack_forget()
        else:
            self.refresh_button.pack(side='right', padx=(8,0))
            self.add_button.pack(side='right')

    def add_action(self):
        if self.scope == 'remote' and not self.remote:
            self.show_connection_form()
        else:
            self.show_login()

    def add_server(self):
        self.show_connection_form()

    def show_connection_form(self):
        self.leave_login()
        self.close_scope_menu()
        self.scope = 'remote'
        self.scope_button.configure(text='Remote')
        self.scope_hint.configure(text='Verbundene Rechner')
        self.page = 'connect'
        self.form_error = None
        self.connection_form = {key:tk.StringVar(value=value) for key,value in [
            ('name',''),('host',''),('command',''),('home','')]}
        self.connection_advanced = tk.BooleanVar(value=False)
        self.render()

    def go_back(self):
        self.leave_login()
        self.close_scope_menu()
        if self.page in {'login','details'}:
            self.page = 'accounts'
        elif self.scope == 'remote':
            self.page = 'connections'
        else:
            self.page = 'accounts'
        self.render()

    def _panel(self, title, subtitle):
        self.view_deadline = float('inf')
        self.rendered = []
        self.card_views = {}
        self.sync_header()
        self.page_title.configure(text=title, wraplength=max(420, self.main.winfo_width()-80))
        self.subtitle.configure(text=subtitle)
        captions={'connections':'Verbindungen über SSH','connect':'Verbindung mit einem entfernten Rechner','login':'Anmeldung auf dem gewählten Rechner','details':'Gemeldeter Account-Stand'}
        self.status_text.configure(text=captions.get(self.page,''))
        for child in self.cards.winfo_children():
            child.destroy()
        for col in range(3):
            self.cards.grid_columnconfigure(col, weight=0, uniform='', minsize=0)
        self.cards.grid_columnconfigure(0, weight=1)
        inner = tk.Frame(self.cards, bg=BG)
        inner.grid(row=0,column=0,sticky='nsew',padx=20,pady=(12,24))
        self.canvas.yview_moveto(0)
        return inner

    def render_panel(self):
        if self.page == 'connections':
            self.render_connections()
        elif self.page == 'connect':
            self.render_connection_form()
        elif self.page == 'login':
            self.render_login()
        elif self.page == 'details':
            self.render_details()

    def render_connections(self):
        inner = self._panel('Verbindungen','Deine entfernten Rechner und ihre verfügbaren Accounts.')
        try:
            connections = RemoteConfig(self.home).all()
        except (OSError, ValueError) as exc:
            self.text(inner, str(exc), color=WARNING, wraplength=550).pack(anchor='w')
            return
        if not connections:
            self.text(inner,'Deine Accounts. Auf jedem Rechner.',size=25).pack(anchor='w',pady=(36,12))
            self.text(inner,'Verbinde einen Linux-Server, um seine Accounts und Kontingente hier zu sehen.',color=MUTED,wraplength=550,justify='left').pack(anchor='w')
            ttk.Button(inner,text='Verbindung hinzufügen',style='Fleet.TButton',command=self.show_connection_form).pack(anchor='w',pady=(24,0))
        self.connection_cards = {}
        for name, config in connections.items():
            row = tk.Frame(inner,bg=SURFACE,highlightthickness=1,highlightbackground=LINE)
            row.pack(fill='x',pady=(0,14))
            content = tk.Frame(row,bg=SURFACE)
            content.pack(fill='x',padx=22,pady=20)
            ttk.Button(content,text='Entfernen',style='Soft.TButton',command=lambda n=name:self.remove_connection(n)).pack(side='right',padx=(8,0))
            ttk.Button(content,text='Öffnen',style='Soft.TButton',command=lambda n=name:self.select_remote(n)).pack(side='right')
            self.text(content,name,size=24,bold=True,bg=SURFACE,image=self.theme.icon('server'),compound='left').pack(anchor='w')
            self.text(content,config['host'],size=13,color=MUTED,bg=SURFACE).pack(anchor='w',pady=(6,8))
            info = self.remote_summaries.get(name)
            if info is None:
                caption,tone='Wird geprüft …',MUTED
            elif info.get('error'):
                caption,tone='Nicht erreichbar · Erneut versuchen',WARNING
            else:
                count=sum(bool(a.get('connected')) for a in info.get('accounts',[]))
                caption,tone=f"{count} Accounts verbunden",GREEN
            label=self.text(content,caption,size=13,color=tone,bg=SURFACE)
            label.pack(anchor='w')
            self.connection_cards[name]={'frame':row,'status':label}

    def remove_connection(self,name):
        try:
            RemoteConfig(self.home).remove(name)
        except (ValueError,OSError) as exc:
            self.status_text.configure(text=redact(str(exc)))
            return
        self.remote_summaries.pop(name,None)
        if self.remote==name:
            self.remote=None
            self.target_epoch+=1
            self.accounts=[]
        self.page='connections'
        self.render_connection_nav()
        self.render()

    def _entry(self,parent,label,variable,*,width=42):
        row=tk.Frame(parent,bg=BG)
        row.pack(fill='x',pady=(0,18))
        self.text(row,label,size=13,bold=True).pack(anchor='w',pady=(0,7))
        entry=ttk.Entry(row,textvariable=variable,style='Fleet.TEntry',font=self.theme.face(16),width=width)
        entry.pack(fill='x')
        return entry

    def render_connection_form(self):
        inner=self._panel('Rechner verbinden','Verbinde einen Server mit deinem vorhandenen SSH-Zugang.')
        form=tk.Frame(inner,bg=BG)
        form.pack(anchor='w',fill='x',padx=(0,20))
        self.connection_name_entry=self._entry(form,'Name',self.connection_form['name'])
        self._entry(form,'SSH-Adresse oder Alias',self.connection_form['host'])
        self.text(form,'Agent Fleet erkennt Installation und Datenverzeichnis auf dem Server automatisch.',size=13,color=MUTED,wraplength=570,justify='left').pack(anchor='w',pady=(0,18))
        ttk.Checkbutton(form,text='Erweiterte Einstellungen',variable=self.connection_advanced,style='Fleet.TCheckbutton',command=self.render).pack(anchor='w',pady=(0,16))
        if self.connection_advanced.get():
            self._entry(form,'Agent-Fleet-Datei auf dem Server',self.connection_form['command'])
            self._entry(form,'Datenverzeichnis auf dem Server',self.connection_form['home'])
        if self.form_error:
            self.text(form,self.form_error,color=WARNING,wraplength=580,justify='left').pack(anchor='w',pady=(0,16))
        self.connect_button=ttk.Button(form,text='Verbinden',style='Fleet.TButton',command=self.save_connection)
        self.connect_button.pack(anchor='w')
        if self.form_busy:
            self.connect_button.configure(state='disabled',text='Verbindung wird geprüft …')

    def save_connection(self):
        if self.form_busy:
            return
        values={k:v.get().strip() for k,v in self.connection_form.items()}
        if not values['name'] or not values['host']:
            self.form_error='Gib einen Namen und eine SSH-Adresse ein.';self.render();return
        self.form_busy=True;self.form_error=None
        self.connect_button.configure(state='disabled',text='Verbindung wird geprüft …')
        token=uuid.uuid4().hex
        self.connection_request=token
        advanced=self.connection_advanced.get()
        def action():
            if advanced:
                config={'host':values['host'],'command':values['command'],'home':values['home']}
            else:
                config=discover(values['host'])
            data=RemoteClient(config).data(['status'])
            if 'native-login-sessions' not in data.get('features',[]):
                raise ValueError('Bitte Agent Fleet auf dem Server aktualisieren, um den Login in der App zu nutzen.')
            RemoteConfig(self.home).add(values['name'],config['host'],config['command'],config['home'])
            return {'name':values['name'],'data':data}
        self.run_panel_action('connect',token,action)

    def probe_connections(self):
        if self.probing_connections:
            return
        try:configs=RemoteConfig(self.home).all()
        except (OSError,ValueError):return
        self.probing_connections=True
        def action():
            from concurrent.futures import ThreadPoolExecutor
            def probe(item):
                name,config=item
                try:return name,RemoteClient(config).data(['status'])
                except Exception as exc:return name,{'error':redact(str(exc))}
            with ThreadPoolExecutor(max_workers=3) as pool:
                return dict(pool.map(probe,configs.items()))
        self.run_panel_action('connections','summary',action)

    def show_login(self, account=None):
        self.leave_login()
        self.close_scope_menu()
        self.page='login'
        self.login_form={
            'provider':tk.StringVar(value=(account or {}).get('provider','codex')),
            'name':tk.StringVar(value=(account or {}).get('name','')),
            'code':tk.StringVar()}
        self.login_state=None
        self.login_error=None
        self.login_busy=False
        self.login_key=uuid.uuid4().hex
        self.login_target=self.remote
        self.login_spec=None
        self.login_client=None
        if self.remote:
            try:self.login_client=RemoteClient(RemoteConfig(self.home).get(self.remote))
            except (ValueError,OSError) as exc:self.login_error=redact(str(exc))
        self.render()

    def render_login(self):
        target=self.login_target or 'diesem Rechner'
        inner=self._panel('Account verbinden',f'Die Anmeldung bleibt auf {target}.')
        form=tk.Frame(inner,bg=BG)
        form.pack(fill='x',padx=(0,20))
        state=self.login_state
        if state is None:
            self.text(form,'Anbieter',size=13,bold=True).pack(anchor='w',pady=(0,8))
            choices=tk.Frame(form,bg=BG);choices.pack(anchor='w',pady=(0,24))
            self.login_provider_buttons={}
            for provider,caption in [('codex','Codex · ChatGPT'),('claude','Claude')]:
                button=ttk.Radiobutton(choices,text=caption,value=provider,variable=self.login_form['provider'],style='Compact.TRadiobutton')
                button.pack(side='left',padx=(0,16));self.login_provider_buttons[provider]=button
            self.login_name_entry=self._entry(form,'Name für diesen Account',self.login_form['name'])
            self.text(form,'Zum Beispiel Privat oder Arbeit. Ein bestehender Account kann hier erneut angemeldet werden.',size=13,color=MUTED,wraplength=550,justify='left').pack(anchor='w',pady=(0,22))
            self.login_start_button=ttk.Button(form,text='Anmeldung starten',style='Fleet.TButton',command=self.start_login)
            self.login_start_button.pack(anchor='w')
            if self.login_busy:self.login_start_button.configure(state='disabled',text='Anmeldung wird vorbereitet …')
        else:
            provider='Codex' if state['provider']=='codex' else 'Claude'
            self.text(form,provider+' · '+state['profile'],size=24,bold=True).pack(anchor='w',pady=(0,12))
            self.text(form,state['message'],size=16,color=GREEN if state['state']=='succeeded' else MUTED,wraplength=580,justify='left').pack(anchor='w',pady=(0,20))
            if state.get('device_code'):
                self.text(form,'Dein einmaliger Gerätecode',size=12,color=MUTED).pack(anchor='w')
                code_entry=ttk.Entry(form,style='Fleet.TEntry',font=self.theme.face(28,True),width=18)
                code_entry.insert(0,state['device_code']);code_entry.configure(state='readonly');code_entry.pack(anchor='w',pady=(8,12))
                ttk.Button(form,text='Code kopieren',style='Soft.TButton',command=self.copy_device_code).pack(anchor='w',pady=(0,18))
            if state.get('url'):
                ttk.Button(form,text='Im Browser anmelden',style='Fleet.TButton',image=self.theme.icon('box-arrow-up-right','white'),compound='left',command=self.open_login_url).pack(anchor='w',pady=(0,18))
            if state['state']=='awaiting_code':
                self.login_code_entry=self._entry(form,'Code aus dem Browser',self.login_form['code'])
                self.login_code_entry.configure(show='•')
                ttk.Button(form,text='Anmeldung abschließen',style='Fleet.TButton',command=self.submit_login_code).pack(anchor='w',pady=(0,12))
            if state['state'] in ACTIVE:
                ttk.Button(form,text='Anmeldung abbrechen',style='Soft.TButton',command=self.cancel_login).pack(anchor='w',pady=(12,0))
            elif state['state']=='succeeded':
                ttk.Button(form,text='Zur Übersicht',style='Fleet.TButton',command=self.finish_login).pack(anchor='w')
            else:
                ttk.Button(form,text='Erneut versuchen',style='Fleet.TButton',command=lambda:self.show_login({'name':state['profile'],'provider':state['provider']})).pack(anchor='w')
        if self.login_error:
            self.text(form,self.login_error,color=WARNING,wraplength=580,justify='left').pack(anchor='w',pady=(18,0))

    def login_call(self,argv,client):
        if client:
            return client.data(argv)
        from .rpc import handle
        result=handle(self.home,{'version':1,'argv':argv})
        data=json.loads(result['output'])
        if result['code']!=0:raise ValueError(data.get('error','Anmeldung nicht möglich'))
        return data

    def start_login(self):
        if self.login_busy:return
        provider=self.login_form['provider'].get()
        name=re.sub(r'[^a-z0-9-]+','-',self.login_form['name'].get().strip().casefold()).strip('-')[:48]
        if name and not name[0].isalpha():name=provider+'-'+name[:40]
        if not name:
            self.login_error='Gib einen Profilnamen ein.';self.render();return
        if self.login_target and self.login_client is None:
            self.login_error='Diese Verbindung ist nicht mehr verfügbar. Kehre zur Verbindungsübersicht zurück.';self.render();return
        spec=(provider,name)
        if self.login_spec is not None and self.login_spec!=spec:
            self.leave_login()
            self.login_key=uuid.uuid4().hex
        self.login_spec=spec
        self.login_busy=True;self.login_error=None
        token=self.login_key
        self.login_start_button.configure(state='disabled',text='Anmeldung wird vorbereitet …')
        client=self.login_client
        self.run_panel_action('login',token,lambda:self.login_call(['auth','start',name,'--provider',provider,'--key',token],client))

    def cancel_login_timer(self):
        if self.login_poll_id:
            try:self.root.after_cancel(self.login_poll_id)
            except tk.TclError:pass
            self._after_ids.discard(self.login_poll_id)
            self.login_poll_id=None

    def schedule_login_poll(self):
        self.cancel_login_timer()
        if self.closed or self.login_busy or self.login_poll_inflight or not self.login_state or self.login_state['state'] not in ACTIVE:return
        token=self.login_key
        self.login_poll_id=self._schedule(1200,lambda:self.poll_login(token))

    def poll_login(self, token):
        self.login_poll_id=None
        if self.closed or token!=self.login_key or self.login_poll_inflight or not self.login_state or self.login_state['state'] not in ACTIVE:return
        self.login_poll_inflight=True
        client=self.login_client;ident=self.login_state['id']
        self.run_panel_action('login_poll',token,lambda:self.login_call(['auth','get',ident],client))

    def leave_login(self, detached=False):
        self.cancel_login_timer()
        if not self.login_key or (not self.login_busy and (not self.login_state or self.login_state['state'] not in ACTIVE)):
            return
        token=self.login_key
        ident=(self.login_state or {}).get('id',token)
        client=self.login_client
        target=self.login_target
        self.login_key=None
        self.login_state=None
        self.login_poll_inflight=False
        self.login_busy=False
        if detached:
            from .login_sessions import launch_cancel
            try:launch_cancel(self.home,target,ident)
            except (OSError,ValueError):pass
        else:
            self.run_panel_action('abandon_login',token,lambda:self.login_call(['auth','cancel',ident],client))

    def submit_login_code(self):
        if self.login_busy:return
        code=self.login_form['code'].get().strip()
        if not code:
            self.login_error='Füge den Code aus dem Browser ein.';self.render();return
        self.login_busy=True
        self.login_form['code'].set('')
        client=self.login_client;ident=self.login_state['id'];token=self.login_key
        def action():
            self.login_call(['auth','input',ident,'--code='+code],client)
            return self.login_call(['auth','get',ident],client)
        self.run_panel_action('login_input',token,action)

    def cancel_login(self):
        if not self.login_state:return
        client=self.login_client;ident=self.login_state['id'];token=self.login_key
        def action():
            self.login_call(['auth','cancel',ident],client)
            return self.login_call(['auth','get',ident],client)
        self.run_panel_action('login_input',token,action)

    def open_login_url(self):
        url=(self.login_state or {}).get('url')
        if url and safe_url(url):webbrowser.open(url)

    def copy_device_code(self):
        code=(self.login_state or {}).get('device_code')
        if code:
            self.root.clipboard_clear();self.root.clipboard_append(code)

    def finish_login(self):
        self.page='accounts'
        self.show_all.set(True)
        self.render()
        self.refresh()

    def render_details(self):
        account=self.detail_account
        inner=self._panel(account.get('display_name') or account['name'],account.get('email') or 'Account-Details')
        for label,value in [('Profil',account['name']),('Tarif',account['plan_label']),('Status',account['status_label']),('Datenstand',account['updated_label'])]:
            self.text(inner,label,size=12,color=MUTED).pack(anchor='w',pady=(10,4))
            self.text(inner,value,size=17).pack(anchor='w')
        for window in account['windows_view']:
            self.text(inner,window['title'],size=15,bold=True).pack(anchor='w',pady=(22,6))
            value='Kein aktueller Wert' if window['remaining'] is None else f"{window['remaining']:g} % frei"
            self.text(inner,value+' · '+window['reset_label'],size=15,color=MUTED,wraplength=550).pack(anchor='w')
        if account.get('error'):
            self.text(inner,account['error'][:600],size=13,color=WARNING,wraplength=560).pack(anchor='w',pady=(18,0))
        if account.get('managed'):
            ttk.Button(inner,text='Erneut anmelden',style='Soft.TButton',command=lambda:self.show_login(account)).pack(anchor='w',pady=(26,0))

    def run_panel_action(self,kind,token,action):
        def run():
            try:result={'kind':kind,'token':token,'data':action()}
            except Exception as exc:result={'kind':kind,'token':token,'error':redact(str(exc))[:700]}
            self.events.put(('panel',result,None))
        threading.Thread(target=run,daemon=True,name='fleet-'+kind).start()

    def handle_panel_event(self,event):
        kind=event['kind']
        if kind=='connections':
            self.probing_connections=False
            self.remote_summaries.update(event.get('data',{}))
            if self.page=='connections':self.render()
        elif kind=='connect' and event['token']==self.connection_request:
            self.form_busy=False
            if event.get('error'):
                self.form_error=event['error']
                if self.page=='connect':self.render()
            else:
                data=event['data'];self.remote_summaries[data['name']]=data['data']
                self.render_connection_nav()
                if self.page=='connect':self.select_remote(data['name'])
        elif kind in {'login','login_input','login_poll'} and event['token']==self.login_key:
            if kind=='login_poll':self.login_poll_inflight=False
            else:self.login_busy=False
            if event.get('error'):
                self.login_error=event['error']
            else:
                previous=self.login_state
                incoming=event['data']
                if previous and incoming.get('updated_at',0)<previous.get('updated_at',0):
                    self.schedule_login_poll();return
                self.login_state=incoming;self.login_error=None
                keys=('state','url','device_code','message')
                if previous and all(previous.get(k)==self.login_state.get(k) for k in keys):
                    self.schedule_login_poll()
                    return
            if self.page=='login':self.render()
            if self.login_state and self.login_state['state'] in ACTIVE:
                self.schedule_login_poll()
