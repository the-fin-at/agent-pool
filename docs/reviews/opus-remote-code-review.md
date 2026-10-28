# Opus 5.5 – Prüfung der Implementierung

Native Claude-CLI, exaktes Modell `claude-opus-5-5`, ohne Tools. Dieses Gutachten bezieht sich auf einen Zwischenstand; behobene Befunde stehen in `../remote-decisions.md`.

# Review: Remote-Implementierung (Opus 5.5)

**Kurzurteil:** Die Kernanforderung ist erfüllt. Der RPC kann keine Inferenz-Jobs ausführen, und die Races zwischen Abbrechen und Starten sind behoben. Es bleiben ein echter Betriebsbug im Worker, einige Mängel in GUI und Protokoll sowie mehrere Inkonsistenzen.

---

## Echte Bugs

### 1. Worker läuft in einer Busy-Loop, solange ein Profil-Lock belegt ist (`worker.py` `tick`)
`run_native` liefert sofort `Outcome("busy")`. Danach setzt `tick` den Job auf `waiting` und gibt `True` zurück. Weil `did_work=True` ist, schläft `work` nicht und claimt sofort erneut.

Das passiert, solange `login` (Minuten) oder eine Metadaten-Session (bis 20 s pro Profil) den `.native.lock` hält. In dieser Zeit entsteht eine Schleife mit 100 % CPU und mehreren SQLite-Commits pro Iteration (`claim_job`, `last_used`, `update_job`). Nach Bug 2 tritt das regelmäßig auf.

**Fix:** Bei `busy` entweder einen kurzen Hold setzen (`hold_until=now+10`, `hold_reason="busy"`) oder `False` zurückgeben bzw. pausieren.

### 2. Der Remote-Desktop startet jede Minute native Prozesse im RPC
`Dashboard.refresh` ruft remote `status --refresh` auf. `collect` startet dann pro Codex-Profil `codex app-server` im kurzlebigen, SSH-gebundenen RPC-Prozess. Mehrere offene Desktops (Mac und Windows) vervielfachen das. Das ist kein Job, widerspricht aber dem Ziel aus 1.2 des Vorgutachtens: „Remote-Monitor liest nur den Cache.“

Folgen:
- Lock-Konkurrenz mit dem Worker, was Bug 1 auslöst.
- Bei SIGHUP wird der RPC ohne `finally` beendet. Ob `app-server` (eigene Session) bei EOF auf stdin zuverlässig endet, ist nicht verifiziert.

**Fix:** Das Auto-Refresh remote auf `status` ohne `--refresh` umstellen. `--refresh` nur auf expliziten Klick senden, oder die Abfragen ganz dem Worker überlassen.

### 3. `Manager` im lokalen Modus nutzt `redirect_stdout` aus Threads
`rpc.handle` tauscht das prozessglobale `sys.stdout` aus. `busy` serialisiert nur innerhalb eines Fensters, aber „Aufträge“ lässt sich mehrfach öffnen. Zwei parallele `handle()`-Aufrufe vertauschen dann ihre Ausgaben:
- JSON landet im falschen Puffer.
- Die Wiederherstellung in falscher Reihenfolge lässt `sys.stdout` dauerhaft auf einem `StringIO` stehen.

**Fix:** Für den lokalen Modus reine Funktionen nutzen, die Werte zurückgeben statt `emit`. Mindestens ein globales `threading.Lock` um `handle` legen.

### 4. `Manager` behält den Auftragsschlüssel nach erfolgreichem Submit
Der Hinweistext gilt nur für Verbindungsfehler. Nach einem Erfolg passiert Folgendes:
- Gleicher Prompt erneut gesendet: Der alte Job wird **still** zurückgegeben, und der Nutzer glaubt an einen neuen Auftrag.
- Geänderter Prompt: Es kommt ein unverständlicher Konflikt.

**Fix:** Bei `kind == "submit"` automatisch `new_key()` aufrufen.

### 5. `Dashboard.refresh` kann dauerhaft hängen
`self.refreshing = True` wird gesetzt, bevor `RemoteConfig(...).get(...)` im UI-Thread läuft. Wirft das, etwa weil die Remote gelöscht oder `remotes.json` defekt ist, bleibt der Button für immer auf „Abfrage läuft …“.

**Fix:** Den Lookup vor das Setzen des Flags ziehen oder per `try` absichern.

### 6. Der RPC-Stream ist durch `-h`/`--help` verschmutzbar
`parse_args` läuft nur mit umgeleitetem stderr. `job submit -h` schreibt Hilfetext auf das echte stdout, bevor die JSON-Zeile folgt, und der Client meldet „Invalid remote JSON“. Das hat keine Seiteneffekte.

**Fix:** stdout ebenfalls umleiten oder `add_help=False` für den RPC-Parser.

### 7. Kleinere Robustheitsmängel
- `validate()`: Ist `"command": null` in `remotes.json` eingetragen, wirft `command.startswith` einen `AttributeError` statt `ValueError`, und der Fehler landet in einer Tk-Callback-Exception.
- `serve()`: Ein tief verschachteltes JSON erzeugt `RecursionError`, andere Exceptions aus `handle` erzeugen einen Traceback statt einer JSON-Antwort. Der Client meldet daraufhin fälschlich „Submission may have reached the server“.

---

## Inkonsistenzen (kein Blocker)

- **Client und Server widersprechen sich:**
  - `dispatch_remote` erlaubt `init`, der RPC lehnt es ab.
  - `quota set` lehnt der Client ab, der RPC würde es erlauben.

  Die Allowlists sollten aus einer gemeinsamen Quelle kommen.
- **`acknowledge_review` gilt nur im RPC.** Ein lokales `job retry` auf `needs_review` braucht das Flag nicht. Die Prüfung gehört in `dispatch` bzw. `transition_job`.
- **Irreführende Meldung bei laufenden Jobs:** „Recover the stopped worker first with `work --once`“ erscheint auch, wenn der Worker gesund läuft. Remote ist der Hinweis zudem nicht ausführbar, und auf dem Server liefert er `WorkerBusy`.
- **Falsche Annahme im lokalen Manager:** Er zeigt „Der Worker auf dem Server führt …“ an, obwohl lokal womöglich gar kein Worker läuft.

---

## Bestätigt korrekt

- **RPC führt keine Jobs aus.** Die Allowlist enthält weder `run`, `work`, `login`, `init`, `service`, `remote` noch `rpc`.
  - Root-Optionen nach dem Subcommand lässt argparse nicht zu, `--home`/`--remote` sind also nicht injizierbar.
  - `workspace add/remove` und `profile add` sind gesperrt.
- **Abbruch gegen Start:** `claim_job` mit `BEGIN IMMEDIATE` und bedingtem UPDATE, dazu `transition_job` mit `rowcount` für cancel, retry und waiting. Die Race ist geschlossen.
- **Running-Jobs:** Nur der Lock-Halter setzt `running`, und `recover()` beim Start ist korrekt.
- **Lock-Modell:**
  - `worker_lock` ist nur noch ein Executor-Lease. Steuerbefehle laufen ohne `WorkerBusy`.
  - Ein Profil-Lock schützt `run_native`, die Metadaten-Session und `login`.
  - Ein `login` während eines laufenden Jobs scheitert sauber.
- **SIGTERM und systemd:**
  - Der SIGTERM-Handler löst `KeyboardInterrupt` aus. Das führt zu `stop_process`, setzt `needs_review` und beendet den Heartbeat.
  - `KillMode=control-group` erfasst auch Kindprozesse mit eigener Session.
  - Exit 130 bei `systemctl stop` löst keinen Neustart aus.
  - Das Escaping von `%`/`$` in der Unit ist korrekt.
- **SSH-Kommando:**
  - Der Host-Regex verhindert einen führenden `-` und `=`, Konfig-Tokens werden per `shlex.join` übergeben.
  - Prompts gehen nur über stdin.
  - `BatchMode`, `StrictHostKeyChecking=yes`, `ForwardAgent=no` und die Timeouts sind gesetzt.
- **Protokoll:**
  - Strikte Felder, Versionsprüfung und 2 MiB-Limit vor dem Parsen.
  - Ungültiges UTF-8, Surrogates und NUL werden abgelehnt.
  - Antwortlimit, Exit-Codes 0/1/2 und explizites UTF-8 beidseitig. Windows-CRLF ist unkritisch, da JSON keine rohen Zeilenumbrüche enthält.
- **Remote-Ablauf:**
  - `run` remote läuft als submit + wait (≤ 60 s) bei einem Client-Timeout von 120 s.
  - `--key` ist Pflicht, und Timeout-Meldungen fordern explizit dazu auf, denselben Key wiederzuverwenden.
  - `--cwd` und `--prompt-file` lehnt der RPC ab.
- **Eingabegrenzen und Workspaces:**
  - Regex für Modell und Bucket ohne führenden `-`.
  - Timeout ≤ 4 h, Versuche ≤ 100, NaN/inf werden abgefangen.
  - Der Symlink-Tausch wird beim Submit und in `tick` erkannt.
- **Laufzeit:**
  - Der Heartbeat liegt in einer separaten Datei und berührt den Lease nicht.
  - Die SSH-Variablen werden aus `environment()` entfernt.
- **GUI:** Netzwerk- und DB-Zugriffe laufen in Threads und werden per `queue` + `after()` übergeben. `target_epoch` verwirft veraltete Antworten nach einem Zielwechsel korrekt.

---

## Empfehlungen (nach Priorität)

1. **Fester Server-Home.** Erst Bug 1 und 2 beheben. Danach `server-home` in `remote add` und im Desktop-Dialog zur Pflicht machen. Sonst entstehen zwei Queues, sobald `AGENT_POOL_HOME` nur in der interaktiven Shell gesetzt ist (Unit mit `--home`, RPC ohne).
2. **`doctor` erweitern:** Linger (`loginctl show-user`), dateibasierten Credential-Store pro Profil und das Home des Workers (aus `worker-status.json`) prüfen.
3. **SIGHUP im RPC:** Ein Handler mit `KeyboardInterrupt` oder `signal.SIG_IGN` während `--refresh`, solange dort noch native Prozesse laufen.
4. **`job list` begrenzen:** Limit oder Paginierung, damit das 10 MiB-Limit langfristig nicht greift.
5. **Gemeinsame Op-Tabelle** für CLI-Remote, RPC-Allowlist und Manager, siehe Inkonsistenzen.
6. **Dokumentation:** Die Login-Shell auf dem Server muss POSIX-kompatibel sein (wegen `shlex.join`), z. B. kein fish.

**Freigabeempfehlung:** Nach Behebung von Bug 1–4 ist das MVP für den Single-User-Betrieb tragfähig. Bug 5–7 und die Inkonsistenzen können im Folge-Commit behoben werden.