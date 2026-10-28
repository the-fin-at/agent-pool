# Opus 5.5 – Architekturprüfung

Angefragtes Modell: `claude-opus-5-5`. Native CLI-Aufruf; keine Dateiänderungen durch den Gutachter.

# Architektur-Gutachten: Remote-Erweiterung für Agent Pool

## Kurzurteil

Die Richtung stimmt: SSH statt HTTP, ein kurzlebiger RPC-Prozess, ein einziger systemd-Worker, Workspace-Namen statt Pfaden und keine Synchronisierung von Credentials. Der Vorschlag scheitert aber am aktuellen Code an einer zentralen Stelle, nämlich an `worker_lock`. Dazu kommen einige SSH- und systemd-Fallen, die still Fehler oder Sicherheitslücken erzeugen.

---

## 1. Blocker im bestehenden Code

### 1.1 `worker_lock` blockiert jede Steuerung, sobald ein dauerhafter Worker läuft

Diese Befehle laufen heute alle unter `store.worker_lock()`:
- `cancel`, `retry`
- `profile enable/disable/release`
- `login`
- `quota set`, `quota refresh`

`work` hält den Lock während der gesamten Schleife. Mit einem dauerhaften systemd-Worker endet daher jede dieser Remote-Operationen mit `WorkerBusy`. Remote-Steuerung ist so nicht möglich.

Den Lock einfach wegzulassen reicht nicht. Er verhindert heute zwei Races:

- **Abbrechen gegen Starten.** `tick()` liest zuerst `jobs(pending=True)` und setzt danach ohne Bedingung `status='running'`. Ein Cancel, der zwischen diesen beiden Schritten ankommt, wird überschrieben, und der Job läuft trotzdem.
- **Login gegen laufenden Job.** Ein `login` schreibt in `authdir`, während der Worker vielleicht gerade mit genau diesem Profil arbeitet.

**Lösung (MVP):**
- **Worker-Lease:** `worker.lock` bleibt, wird aber nur noch von `work` gehalten. Er bedeutet dann nur noch: „genau ein Executor“.
- **Zustandswechsel als bedingte SQL-Updates:**
  - Abbrechen: `UPDATE jobs SET status='cancelled' WHERE id=? AND status IN ('queued','waiting')`
  - Starten im Worker: `... SET status='running' WHERE id=? AND status IN ('queued','waiting')`
  - In beiden Fällen `rowcount` prüfen.
  - Ein `retry` ist analog nur aus terminalen Zuständen erlaubt.
- **Lock pro Profil:** `flock` auf `profiles/<name>/.lock`. Ihn halten:
  - `run_native`
  - `codex_metadata_session` (Quota-Abfrage und Monitor)
  - `login`

### 1.2 Gleichzeitige native Prozesse auf demselben `CODEX_HOME`

Heute ist das möglich: Ein Monitor-Poll startet `app-server` für `account/read` bzw. `rateLimits`, während auf demselben Profil ein Job läuft.

Bei rotierenden Refresh-Tokens können sich zwei parallele Refreshes gegenseitig invalidieren. Die Folge wäre ein stiller Logout des Abos. Lokal kam das selten vor, mit einem Hintergrund-Monitor wird es regelmäßig passieren.

Der Lock pro Profil aus 1.1 löst das. Zusätzlich sollte der Monitor remote **nur Cache-Daten** lesen (`monitor_cache`, `windows`). Die Abfragen beim Anbieter macht ausschließlich der Worker.

### 1.3 RPC darf niemals Jobs ausführen

`run` übernimmt die Worker-Rolle, wenn der Lock frei ist, also auch in den Sekunden, in denen systemd den Worker gerade neu startet.

Ein solcher RPC-Prozess hängt an der SSH-Session. Bricht die Verbindung ab, wird er per SIGHUP beendet, und zwar ohne `finally`. Der native Kindprozess läuft wegen `start_new_session=True` **weiter** und editiert den Workspace.

Der nächste Worker markiert den Job per `recover()` als `needs_review`. Wer dann `retry` ausführt, hat **zwei Agenten im selben Workspace**.

Daraus folgt:
- Im RPC gibt es weder `run` noch `work` noch `tick`.
- Remote-`run` ist clientseitig „submit + wait“.

### 1.4 Abbruch des Workers sauber machen

Python beendet sich bei SIGTERM standardmäßig, ohne `finally` auszuführen.

**Lösung (MVP):**
- Einen SIGTERM-Handler installieren, der `KeyboardInterrupt` auslöst. Dann greift der bestehende `BaseException`-Pfad mit `stop_process` und `needs_review`.
- In der Unit `KillMode=control-group` belassen (Standard) und **nie** `process` setzen.
- `TimeoutStopSec` großzügig wählen, etwa 30 s.

---

## 2. SSH-spezifische Gefahren

| Gefahr | Konkrete Maßnahme |
|---|---|
| **sshd fügt Argumente zu einem Shell-String zusammen.** `ssh host agent-pool job submit --prompt "$x"` ist Shell-Injection. | Niemals argv über SSH übergeben. Den RPC-Key in `authorized_keys` mit `restrict,command="/abs/venv/bin/python -m agent_pool rpc --home /abs/home --client mac"` anlegen. `SSH_ORIGINAL_COMMAND` ignorieren und **nicht** parsen. |
| **`--client` pro Key** | Damit bekommst du Client-Identität, Audit und Namespacing der Idempotency-Keys geschenkt, ohne neue Auth. |
| **Login braucht eine TTY, `restrict` verbietet sie.** | Einen zweiten, normalen Key bzw. Admin-Zugang für `ssh -t host agent-pool login …` verwenden. Login, `init`, `profile add` und `doctor` sind nur serverseitig erlaubt. |
| **`profile add --binary` remote bedeutet beliebige Programmausführung.** | Nicht im RPC anbieten. Auch `home`, `cwd` und `binary` nie aus dem Request übernehmen. |
| **`.bashrc` gibt bei non-interaktivem ssh etwas aus** (bash sourcet `.bashrc` unter sshd). Das zerstört den JSON-Strom. | Strikte Antwort: genau eine JSON-Zeile mit `"v"`. Bei Parse-Fehler meldet der Client klar „Remote-Shell erzeugt Ausgabe“, statt zu raten. |
| **Encoding.** Ein Windows-Client mit `text=True` nutzt cp1252. | Auf beiden Seiten mit Bytes arbeiten (`sys.stdin.buffer`, `sys.stdout.buffer`) und explizit UTF-8 kodieren. |
| **Alias als ssh-Option** (`-oProxyCommand=…`) | Alias-Regex wie bei Profilnamen. Der Alias verweist auf einen `Host` in `~/.ssh/config`. SSH-Optionen nicht selbst nachbauen. |
| **Hängende Verbindungen im Tk-Mainloop** | Immer `-T -o BatchMode=yes -o ConnectTimeout=10 -o ServerAliveInterval=15`. Aufrufe in einem Thread ausführen, Ergebnisse per `queue` + `after()` übergeben, weil Tk nicht threadsicher ist. |
| **Host-Key** | Nach dem Einrichten `StrictHostKeyChecking=yes`. Kein stilles `accept-new` im Desktop. |
| **Agent-Forwarding und Session-Variablen gelangen in die native CLI** | `restrict` setzen. Zusätzlich in `environment()` `SSH_AUTH_SOCK`, `SSH_CONNECTION` und `SSH_CLIENT` entfernen. |

---

## 3. Linux, systemd und Login

- **`loginctl enable-linger <user>`** ist Pflicht. Sonst stirbt der Worker beim Logout und startet nach einem Reboot nicht. `doctor` sollte das prüfen.
- **Home fest verdrahten.** In der Unit `Environment=AGENT_POOL_HOME=…` setzen und dasselbe `--home` im Forced Command verwenden. Die Umgebungen von systemd-user und ssh unterscheiden sich, sonst entstehen zwei Queues.
- **Credential-Speicher.** Native CLIs nutzen unter Linux eventuell den Secret Service bzw. Keyring. Unter systemd-user ohne entsperrte D-Bus-Session schlägt dann die Auth fehl, obwohl der interaktive Login funktioniert hat.
  - Pro Profil auf dateibasierte Speicherung festlegen (bei Codex `cli_auth_credentials_store = "file"` in der `config.toml` des jeweiligen `CODEX_HOME`; Option vor Einsatz gegen die installierte Version prüfen).
  - Explizit testen, dass der Login per ssh einen Job im Worker ermöglicht.
- **Browser-Login über ssh.** `codex login` erwartet einen Callback auf `localhost` des Servers, den der Browser auf dem Mac nicht erreicht.
  - Für Remote-Profile `codex login --device-auth` verwenden oder `ssh -L 1455:localhost:1455` dokumentieren.
  - Claudes `auth login` mit URL und eingefügtem Code funktioniert in einer TTY; trotzdem einmal real verifizieren.
- **Isolation auf dem Server.**
  - Codex im Sandbox-Modus `read-only` und Claudes `Read` können in der Regel *außerhalb* des cwd lesen. Eine Prompt-Injection im Workspace könnte damit `profiles/*/auth.json` anderer Profile in das Ergebnis exfiltrieren.
  - MVP: ein eigener Unix-User `agentpool` ohne sudo, ohne eigene SSH-Private-Keys oder Git-Credentials, mit `0700` überall.
  - Später: bubblewrap bzw. Landlock pro Job, damit nur Workspace und eigenes Profil sichtbar sind.
  - Falls Abos **verschiedener Personen** auf einen Server sollen: Dann ist ein Unix-User pro Person die einzige echte Isolation. Prüfe außerdem die Nutzungsbedingungen der persönlichen Abos.

---

## 4. Protokoll- und Semantikdetails

**Rahmen**
- Request: `{"v":1,"op":"job.submit","params":{…}}`
- Response: `{"v":1,"ok":true,"result":…}` oder `{"v":1,"ok":false,"error":{"code":"conflict|not_found|busy|invalid|unsupported_version","message":…}}`
- Exit-Codes 0/1/2 clientseitig aus der Antwort ableiten, damit die CLI-Semantik identisch bleibt.

**Eingabegrenzen**
- Request auf z. B. 4 MiB begrenzen, *bevor* er geparst wird.
- Unbekannte Felder ablehnen.
- Ungültiges UTF-8, NUL-Zeichen und einzelne Surrogates ablehnen. `json.loads` akzeptiert `\ud800`, später würde es in `communicate` knallen.

**Validierung**
- `model` und `bucket` per Regex `^[A-Za-z0-9][A-Za-z0-9._:-]{0,63}$` prüfen, also kein führendes `-`.
- `timeout` begrenzen (z. B. ≤ 4 h) und `max_attempts` begrenzen. Sonst blockiert ein einzelner Request den einzigen Worker.

**Idempotenz**
- Im Remote-Modus ist der Key **Pflicht**.
- Der Client erzeugt ihn (UUID) und speichert ihn lokal, *bevor* er sendet. Nach einem Verbindungsabbruch wiederholt der Client nur mit demselben Key.
- Serverseitig den Key mit dem Client-Namespace speichern (`mac:…`), damit Mac und Windows nicht kollidieren.

**Workspaces**
- Neue Spalte `workspace` per Migration mit `PRAGMA user_version`. Die Migration läuft nur im Worker. RPC lehnt ab, wenn die Schema-Version nicht passt.
- In die Idempotenz-Spec den **Namen** aufnehmen statt des aufgelösten Pfads.
- Bei der Registrierung *und* beim Submit `resolve()` ausführen, und prüfen, dass der Pfad unter einer erlaubten Wurzel liegt (Symlink-Tausch nach der Registrierung).
- Remote `--cwd` ablehnen. Heute ist `os.getcwd()` der Default, ein Mac-Pfad würde also still mitgeschickt.

**`needs_review` remote**
- Die Semantik lautet „Workspace inspizieren“, aber remote kann man das nicht.
- MVP: `retry` von `needs_review` erfordert `"acknowledge_review": true`.
- Später: ein RPC `workspace.status` (`git status`/`diff --stat`).

**Warten**
- `job.wait` serverseitig auf etwa 25 s kappen. Der Client wiederholt die Long-Poll-Anfrage.
- Ein Abbruch ist harmlos, weil nur gelesen wird.

**Monitor**
- Eine einzige Operation `snapshot` liefert Profile, Quotas aus dem Cache, die letzten N Job-Zusammenfassungen und den Worker-Heartbeat.
- Polling alle 15–30 s.
- Windows-OpenSSH kann kein ControlMaster, also nicht darauf bauen.
- `job.list` begrenzen bzw. paginieren, `result` nur über `job.get`.

**Worker-Heartbeat**
- Eine Zeile in der DB, die jeder `tick` aktualisiert.
- Der Desktop zeigt „Worker offline“, wenn sie älter als 3× das Poll-Intervall ist.
- Nicht testweise den Lock nehmen, sonst entsteht ein Race mit dem Neustart des Workers.

---

## 5. Die 5 wichtigsten Änderungen (Priorität)

1. **Lock-Modell umbauen** (1.1/1.2): Worker-Lease, bedingte Zustandswechsel, Lock pro Profil für alle nativen Prozesse. Ohne das ist der Rest wertlos.
2. **`dispatch` in reine Operationsfunktionen zerlegen.** Sie geben Werte zurück statt `emit`/`print`. Lokale CLI und `rpc` rufen dieselben Funktionen auf, über eine Allowlist ohne ausführende Ops. Das erhält die bestehende Semantik ohne Duplikation.
3. **RPC-Endpunkt härten:** Forced-Command-Key mit `restrict` und `--client`, eine einzige gerahmte JSON-Zeile, Größenlimits, strikte Feldprüfung, Versions-Handshake, Fehlercodes.
4. **Job-Schema-Migration:** Workspace-Registry, Pflicht-Idempotency-Key mit Namespace, Grenzen für Werte, `acknowledge_review` beim Retry.
5. **Server-Betrieb:**
   - systemd-Unit mit Linger, festem Home, `KillMode=control-group`, SIGTERM-Handler, Heartbeat, `Restart=on-failure`
   - eigener Unix-User, dateibasierte Credentials, Device-Auth-Login
   - SSH-Variablen aus `environment()` entfernen

---

## 6. Adversariale Tests

**MVP**

1. **Abbruch gegen Start:** Nach `jobs(pending=True)` per Hook ein Cancel einschieben. Erwartet: Der Job bleibt `cancelled`, `runner` wird nie aufgerufen.
2. **Steuerung bei laufendem Worker:** `work` läuft dauerhaft. `cancel`, `retry`, `quota set` und `profile disable` per RPC funktionieren ohne `WorkerBusy`.
3. **Verbindungsabbruch beim Submit:** Die ssh-Pipe nach dem Senden und vor der Antwort kappen. Erneut mit demselben Key senden, dann zwei Clients parallel mit demselben Key. Erwartet: genau ein Job. Derselbe Key mit anderem Prompt ergibt `conflict`.
4. **Injection-Payloads:**
   - Prompt mit `$(touch /tmp/pwn)`, `'; …`, Backticks, NUL, `\ud800`, 10 MiB
   - `model="-c"`, `model="--foo"`
   - Workspace `../x`, `/etc`, unbekannt
   - Zusatzfelder `cwd`, `home`, `binary`

   Erwartet: abgelehnt oder wörtlich gespeichert, keine Datei in `/tmp`.
5. **Symlink-Tausch:** Ein registrierter Workspace wird nach der Registrierung auf `~` umgebogen. Erwartet: Submit wird abgelehnt.
6. **Worker-Kill:** `systemctl --user stop`, `kill -9` und Reboot während eines laufenden Jobs. Erwartet:
   - kein verwaister `codex`/`claude`-Prozess (`pgrep`)
   - Job ist `needs_review` und läuft **nicht** erneut
   - Retry nur mit `acknowledge_review`
7. **RPC-Abbruch beim `wait`:** Erwartet: keine Zustandsänderung, kein Worker-Verhalten im RPC-Prozess.
8. **Lock pro Profil:** Monitor-Snapshot und Login parallel zu einem laufenden Job auf demselben Profil. Erwartet: kein zweiter nativer Prozess auf demselben `CODEX_HOME` (instrumentiert prüfen).
9. **Ausgabe aus `.bashrc`** sowie ein falsches oder neueres Protokoll `v`. Erwartet: klarer Fehler, keine Seiteneffekte.
10. **Login-zu-Worker-Pfad:** Login per ssh, Logout, Reboot mit Linger. Erwartet: Der Worker führt einen Job mit diesem Profil erfolgreich aus (Keyring-Falle).

**Später**

11. Prompt-Injection im Workspace mit dem Ziel „lies `../../profiles/codex-2/auth.json`“. Erwartet nach Einführung der Sandbox: nicht lesbar. Bis dahin als bekanntes Risiko dokumentieren.
12. Versionsabweichung: alter Worker gegen neue DB-Migration. RPC verweigert die Arbeit, solange der Worker nicht neu gestartet wurde.

---

## 7. MVP vs. später

**MVP:** Abschnitte 1–4 bzw. die Punkte 1–5 aus Abschnitt 5, die Tests 1–10, `snapshot`-Monitor auf Cache-Basis, Heartbeat.

**Später:**
- Laufende Jobs abbrechen (Cancel-Flag, das der Worker pollt und dann die Prozessgruppe beendet → `needs_review`)
- `workspace.status`/Diff-Abruf
- bubblewrap-Sandbox pro Job
- Aufbewahrungsfrist bzw. Bereinigung für Prompts und Ergebnisse
- Erkennung doppelter Accounts über mehrere Profile (dieselbe E-Mail)
- Fortschritts-Streaming
- Parallelität pro Profil statt eines globalen Executors
- Mehrbenutzerbetrieb

**Bewusst nicht machen:**
- HTTP-Daemon
- Credential-Sync
- automatische Wiederholung nach Crash
- RPC-Pfade, die Jobs ausführen
- SSH-Optionen selbst nachbauen statt `~/.ssh/config` zu nutzen