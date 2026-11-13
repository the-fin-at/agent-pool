# Zentraler Agent Fleet auf Linux

Mac- und Windows-Clients übermitteln Aufträge per SSH an einen persönlichen Linux-Server. Dort bleiben native Logins, SQLite-Queue, Quoten und Ergebnisse. Der dauerhafte Worker verarbeitet die Queue auch bei geschlossenem Client. Transport ist OpenSSH; es gibt keinen zusätzlichen HTTP-Port.

## Voraussetzungen

Ein Linux-Server mit passender nativer Rust-CLI, OpenSSH und einer vom Provider unterstützten Codex- bzw. Claude-Code-CLI kann den Pool ausführen. Vorhandene Python-Server bleiben über RPC v1 kompatibel. systemd ist optional, für den beschriebenen Hintergrunddienst aber erforderlich. Ohne systemd kann `agent-fleet work` von einem eigenen Prozess-Supervisor gestartet werden. Entscheidend ist ein dauerhaft laufender Worker unabhängig von der Client-SSH-Verbindung.

Ein eigener Unix-Benutzer ohne sudo empfiehlt sich. Ein Pool ist eine persönliche Vertrauenszone: zugelassene Clients können Aufträge und Ergebnisse aller Profile dieses Pools lesen. Mehrere Personen bekommen getrennte Unix-Benutzer und getrennte Pools. Die Profilverzeichnisse sind keine vollständige Sandbox gegen einen bösartigen Agenten im selben Unix-Account. Es gibt keine Kontingentübertragung zwischen Accounts.

## 1. Auf Linux installieren

Als der Benutzer, der später auch den Worker betreibt:

```sh
git clone https://github.com/the-fin-at/agent-pool.git
cd agent-pool
cargo build -p fleet-cli --release --locked
sh scripts/install_native.sh
export PATH="$HOME/.local/bin:$PATH"
agent-fleet init
agent-fleet doctor
```

Der native Installer überschreibt vorhandene Programme erst mit `--replace` und behält ein Backup. Vor einem Server-Update laufende Ausführungen kontrolliert abwarten, Queue und Poolpfad erhalten und nur den eigenen Worker neu starten. Die [Migration](rust-migration.md) beschreibt den gestuften Betrieb mit älteren Python-Servern. Standard-State auf Linux: `~/.local/share/agent-pool`, auf einer lokalen Platte.

Die Provider-CLIs separat nach deren [Codex-](https://developers.openai.com/codex/cli) und [Claude-Code-Anleitung](https://code.claude.com/docs/en/setup) installieren. `doctor` zeigt fehlende Executables. API-Schlüssel sind für den Abonnementbetrieb nicht nötig.

## 2. Accounts zentral anmelden

Vor dem ersten Workerstart anmelden. Pro Codex-Profil kann unter dessen `CODEX_HOME` die dateibasierte Credential-Speicherung eingestellt werden, damit der Hintergrunddienst keinen Desktop-Keyring benötigt. Eine vorhandene `config.toml` gezielt bearbeiten, statt sie zu überschreiben:

```toml
cli_auth_credentials_store = "file"
```

Beispiel für das erste Profil: `~/.local/share/agent-pool/profiles/codex-1/config.toml`. Danach:

```sh
agent-fleet login codex-1 --device-auth
agent-fleet login codex-2 --device-auth
agent-fleet login codex-3 --device-auth
agent-fleet login claude-1
agent-fleet quota refresh
```

Nur die benötigten Profile anmelden; die übrigen bleiben deaktiviert. Die Codex-Device-Anmeldung muss gegebenenfalls in den persönlichen Sicherheitseinstellungen bzw. Workspace-Berechtigungen erlaubt werden. Der Browser läuft auf deinem Client, der native Login speichert die Credentials auf Linux. [Offizielle Beschreibung von Device-Login und Credential-Speicherung](https://learn.chatgpt.com/docs/auth).

Für eine spätere Neuanmeldung muss der jeweilige Account gerade frei sein. Native Job-, Login- und Metadatenprozesse desselben verwalteten Profils werden durch einen Account-Lock serialisiert. Ein aktiver Account meldet „busy“; wartende Jobs werden dadurch nicht als ausgeführt gezählt.

## 3. Arbeitsverzeichnis registrieren

Die Projekte liegen auf dem Server, etwa als dort ausgechecktes Git-Repository. Agent Fleet synchronisiert keine lokalen Dateien.

```sh
mkdir -p "$HOME/projects/mein-projekt"
agent-fleet workspace add projekt --path "$HOME/projects/mein-projekt"
agent-fleet workspace list
```

Die SSH-Login-Shell auf dem Server muss POSIX-kompatibel sein (z. B. sh oder bash). Der Client verwendet später `--workspace projekt`. Ein lokaler Mac-/Windows-Pfad wird bei Remote-Aufträgen abgelehnt. Verzeichnisse müssen existieren; ein erkannter Wechsel des Symlink-Ziels führt zur Ablehnung bzw. `needs_review`.

## 4. Worker dauerhaft starten

Auf Linux erzeugt dieser Befehl die Unit und zeigt ihren Inhalt. Er installiert oder startet selbst keinen Dienst:

```sh
agent-fleet service --exec "$HOME/.local/bin/agent-fleet"
```

Nach Prüfung als User-Unit speichern und aktivieren:

```sh
mkdir -p "$HOME/.config/systemd/user"
agent-fleet service --exec "$HOME/.local/bin/agent-fleet" > "$HOME/.config/systemd/user/agent-fleet.service"
systemctl --user daemon-reload
systemctl --user enable --now agent-fleet
systemctl --user status agent-fleet
agent-fleet status
```

Damit der User-Dienst ohne Login und nach einem Neustart läuft, muss Linger für diesen Benutzer aktiviert sein. Falls nicht erlaubt, den Serveradministrator `loginctl enable-linger BENUTZER` ausführen lassen. Logs: `journalctl --user -u agent-fleet -f`.

Der Dienst verwendet dasselbe Home wie der Generator, beendet beim Stopp seine gesamte Prozessgruppe und startet nach Fehlern mit Abstand neu. SIGTERM beendet native Prozesse und lässt unsichere Aufträge als `needs_review` stehen. Bei manuellem `kill -9` außerhalb eines Supervisors können Kindprozesse verbleiben: vor einem Retry den Server und Workspace prüfen.

## 5. Mac oder Windows verbinden

Zuerst normalen OpenSSH-Schlüsselzugang einrichten und den Server-Fingerprint über einen vertrauenswürdigen Weg prüfen. Einmal interaktiv `ssh pool-server` ausführen, damit der geprüfte Host-Key bekannt ist. Die App verwendet `BatchMode=yes` und `StrictHostKeyChecking=yes`; Passwort- und Host-Key-Rückfragen sind im Hintergrund deaktiviert. Ein erforderlicher Schlüssel muss im SSH-Agent verfügbar sein.

Beispiel für `~/.ssh/config` (Windows: `%USERPROFILE%\.ssh\config`):

```sshconfig
Host pool-server
    HostName SERVERADRESSE
    User agentpool
    IdentityFile ~/.ssh/id_ed25519
    IdentitiesOnly yes
    ForwardAgent no
```

Clientseitig Agent Fleet installieren. Native Provider-CLIs und lokale Provider-Logins sind für reinen Remote-Betrieb nicht erforderlich. Auf Mac/Linux:

```sh
agent-fleet remote add zentral --host pool-server --command /home/agentpool/.local/bin/agent-fleet --server-home /home/agentpool/.local/share/agent-pool
agent-fleet remote test zentral
agent-fleet --remote zentral status
agent-fleet --remote zentral desktop
```

Auf Windows dieselben Argumente mit der nativen CLI:

```powershell
agent-fleet remote add zentral --host pool-server --command /home/agentpool/.local/bin/agent-fleet --server-home /home/agentpool/.local/share/agent-pool
agent-fleet remote test zentral
agent-fleet --remote zentral desktop
```

Den tatsächlichen Benutzerpfad einsetzen. `--server-home` ist Pflicht und muss exakt dem State-Verzeichnis des Workers entsprechen; dadurch wird eine versehentlich zweite Queue durch unterschiedliche SSH-/Dienst-Umgebungen vermieden. Remotes werden ausschließlich lokal unter `remotes.json` gespeichert. In der Desktop-App oben auf „Remote“ wechseln und „Verbindung hinzufügen“ wählen. Nach dem Öffnen eines Servers stehen seine Accounts und die integrierte Anmeldung bereit; Aufträge übernehmen Agenten über die CLI. Remote-Accounts stammen aus den verwalteten Server-Profilen; der native Hauptaccount des Clients wird nicht in diesen Pool gemischt.

## Aufträge starten und Berichte abholen

```sh
agent-fleet --remote zentral job submit --provider codex --workspace projekt --prompt-file auftrag.txt --key projekt-review-001
agent-fleet --remote zentral job list
agent-fleet --remote zentral job get JOB_ID
agent-fleet --remote zentral job wait JOB_ID --seconds 30
```

`auftrag.txt` wird auf dem Client gelesen und im JSON-Payload über SSH-stdin übertragen. Der Prompt steht nicht im SSH-Shellbefehl. Für Claude `--provider claude --model claude-opus-5-5` verwenden. Für erlaubte Dateibearbeitung zusätzlich `--allow-edits` setzen.

Remote-`run` bedeutet „submit + bis zu 60 Sekunden auf den Serverworker warten“; es startet selbst keinen Executor. Exit-Code 2 bedeutet weiterhin wartend, 0 erfolgreich, 1 Fehler bzw. terminaler Prüfbedarf.

**Unklare Übermittlung:** Nach einem Verbindungsabbruch denselben unveränderten Auftrag mit demselben `--key` erneut senden oder zunächst die Jobs auflisten. Ein anderer Prompt mit gleichem Schlüssel wird abgelehnt. Ein neuer Schlüssel erzeugt absichtlich einen neuen Auftrag. Im Desktop ist der Schlüssel sichtbar; nach einem Fehler bleibt er erhalten, nach bestätigter Speicherung wird für den nächsten Auftrag ein neuer erzeugt. Entwürfe und Schlüssel werden dort nicht über einen App-Neustart hinweg gespeichert.

**Abbruch und Retry:** `job cancel` beendet wartende, noch nicht gestartete Aufträge. Ein bereits laufender Auftrag wird weiter vom Worker betreut. Nach `needs_review` erst mögliche native Prozesse und Änderungen auf Linux prüfen, dann ausdrücklich:

```sh
agent-fleet --remote zentral job retry JOB_ID --acknowledge-review
```

Profil deaktivieren wirkt auf nachfolgende Starts; laufende Jobs werden nicht abgebrochen. Registrierung von Profilen, Änderung von Executables und Registrierung von Workspaces erfolgen direkt auf dem Server. Native Neuanmeldung ist über den normalen SSH-Zugang möglich:

```sh
agent-fleet --remote zentral login codex-1 --device-auth
```

## Optional: eingeschränkter Client-Schlüssel

Für einen reinen Manager-Schlüssel kann der Administrator in `authorized_keys` einen Forced Command verwenden (Pfade einsetzen):

```text
restrict,command="/home/agentpool/.local/bin/agent-fleet --home /home/agentpool/.local/share/agent-pool rpc" ssh-ed25519 PUBLIC_KEY
```

Dieser Schlüssel führt nur den versionierten RPC-Endpunkt aus. `SSH_ORIGINAL_COMMAND` wird ignoriert. Einrichtung und native Logins benötigen einen separaten normalen Admin-SSH-Zugang; `--remote ... login` funktioniert mit dem eingeschränkten Schlüssel nicht. RPC ist eine persönliche Verwaltungsoberfläche einschließlich Modellaufträgen, keine Mehrbenutzer-Sicherheitsgrenze.

## Daten und Grenzen

- Accounts behalten ihre jeweiligen Limits; unbekannte Quoten bleiben unbekannt. Claude-Limits stammen aus beobachteten nativen Ereignissen, nicht aus einem privaten Usage-Endpunkt.
- Unabhängig vom Client können Jobs warten, bis sämtliche relevanten ausgeschöpften Fenster zurückgesetzt sind. Der Serverworker muss dafür laufen.
- Status enthält einen Heartbeat, der auch während langer Jobs aktualisiert wird. Über 35 Sekunden alte Signale gelten als offline. Der Worker aktualisiert Account-Metadaten im Leerlauf spätestens etwa alle 60 Sekunden; während eines langen Jobs bleiben ältere Werte ausdrücklich als solche sichtbar. Clients lesen den Server-Cache, ohne native Metadatenprozesse über SSH zu starten. Offline bedeutet unbestätigte Liveness, nicht automatisch einen abgestürzten Job.
- Request maximal 2 MiB; Response maximal 10 MiB; einzelne Aufgaben maximal vier Stunden und 100 Versuche. Für sehr große Jobhistorien einzelne IDs abrufen; Pagination ist noch offen.
- Prompts und Berichte liegen in der privaten Server-Queue und können Projektinhalte enthalten. Kein Credential-Sync und kein automatischer Dateitransfer.
- Automatische Wiederverbindung wiederholt keine Modellarbeit. Wiederholen unsicherer Modelljobs bleibt eine bewusste Handlung nach Prüfung.

## Nachweise

`python -m unittest discover -s tests -v` prüft die Plattformlogik. `python scripts/test_remote_ssh.py` ist ein zusätzlicher, ausdrücklich gestarteter Test mit Docker, echtem OpenSSH und einer kontrollierten Provider-Test-CLI ohne Accounts. Der Test erzeugt einen temporären Schlüssel und einen nur an Loopback gebundenen Container; beides wird danach entfernt. Er unterbricht die Antwort nach gespeichertem Auftrag und prüft genau eine Ausführung.

Die [Remote-Architektur](remote-decisions.md) und [Validierungsanleitung](validation.md) beschreiben die Grenzen und reproduzierbaren Prüfungen. Testnachweise ersetzen weder einen echten Provider-Login auf einem späteren Server noch native Windows-Abnahme.


## Native Anmeldung über die App ab 0.4

Nach der einmaligen Server- und SSH-Einrichtung können Codex- und Claude-Accounts direkt aus dem Dashboard angemeldet werden. Ein eigenes SSH-Terminal pro Account ist dafür nicht mehr nötig. Browser-Zustimmung und gegebenenfalls Rückgabecode bleiben beim Benutzer. Details: [Übersicht und Login](overview-login.md). Für den aktuellen Login-Ablauf benötigen Client und Server Version 0.4.

## Vorhandenen nativen Server-Account einbinden (0.4.1)

Ein bereits auf demselben Server angemeldeter Account kann ausdrücklich registriert werden, ohne seine Zugangsdaten zu kopieren:

```sh
agent-fleet profile add server-codex --provider codex --binary /absoluter/pfad/codex --auth-home "$HOME/.codex"
agent-fleet profile enable server-codex
```

`--auth-home` ist eine administrative lokale Registrierung auf dem Server, kein RPC-Befehl. Das Verzeichnis muss existieren und dem aktuellen Benutzer gehören. Der gespeicherte aufgelöste Pfad wird bei Verwendung geprüft; doppelte Registrierungen werden abgelehnt. Die Registrierung verändert seine Rechte nicht. Native Provider-Prozesse verwenden dieses vorhandene Verzeichnis einschließlich ihrer regulären Token-Erneuerung. Andere native Prozesse außerhalb des Brokers beachten dessen Account-Lock nicht. Für neu anzumeldende zusätzliche Abos weiterhin die getrennten Standardprofile und den Browser-Login verwenden.

Bei einem Downgrade auf 0.4.0 zuerst angehängte Profile deaktivieren: die alte Version kennt den zusätzlichen Profilpfad nicht. Bestehende isolierte Profile und Queue-Daten werden durch das additive Datenbankfeld erhalten.
