# Installation und Verbindung

## Quelle, Version und Bestand

Quellprojekt: https://github.com/the-fin-at/agent-pool (privat). Fehlenden Repository-Zugriff über den berechtigten GitHub-Account lösen; keine Abos oder Zugangsdaten aus anderen Profilen übernehmen. Bestehenden Checkout anhand seiner Git-Remote identifizieren. Einen schmutzigen Checkout erhalten und in einem separaten Checkout bauen. Für einen neuen Checkout:

```sh
git clone https://github.com/the-fin-at/agent-pool.git
cd agent-pool
```

Repository-Anleitungen nach dem Auschecken lesen: `docs/desktop.md`, `docs/remote.md`, bei vorhandenen Profilen auch `docs/overview-login.md`. Installation und CLI-Vertrag am tatsächlichen Quellstand prüfen. Aktuelle native Provider-Installationswege aus den offiziellen Quellen beziehen: https://developers.openai.com/codex/cli und https://code.claude.com/docs/en/setup. Provider werden nur auf dem ausführenden Rechner benötigt. Unter Windows echte EXEs verwenden; CMD/BAT-Shims werden vom Broker abgelehnt.

Bei vorhandener Installation zuerst Executable/App-Version, State-Verzeichnis, laufende Jobs und Dienste feststellen. Bei einem Update CLI/App/Skills sichern, nicht den Pool ersetzen. Während laufender Aufträge den Worker nicht zum Aktualisieren abbrechen. Binaries und App auf derselben Maschine bereitstellen und gezielt austauschen; nach Prüfung nur den eigenen Agent-Fleet-Worker kontrolliert neu starten. Der Installer bricht vor Änderungen ab, wenn ein Ziel existiert; diese Meldung ist kein Anlass zum Löschen von State oder Skills. Neue Skill-Versionen nach Vergleich gezielt kopieren und eigene Anpassungen erhalten.

## Mac: native CLI und Tauri-App

Ab 0.5 die Rust-/Tauri-Laufzeit verwenden. Rust gemäß `rust-toolchain.toml` und Git sind Buildwerkzeuge; Node.js 24 und die Tauri-Systemvoraussetzungen werden zusätzlich für die App benötigt. Die fertigen Programme brauchen diese Entwicklungswerkzeuge und Python nicht.

```sh
cargo build -p fleet-cli --release --locked
sh scripts/install_native.sh
```

CLI-Ziel ist `~/.local/bin/agent-fleet`. Für Updates nach Vergleich `--replace` verwenden; der Installer behält die vorige Programmdatei als Backup und berührt den Pool nicht. Er installiert ausschließlich Programme. Die Skills `agent-fleet` und `setup-agents-fleet` nach Vergleich aus `skills/` unter `~/.agents/skills` und `~/.claude/skills` übernehmen; eigene Anpassungen und Sicherungen erhalten. `~/.local/bin` in PATH nehmen oder den absoluten Pfad verwenden.

Für die App:

```sh
cd desktop
npm ci
npm run tauri build
cd ..
sh scripts/install_native.sh --desktop --replace
```

Die Quelle liegt unter `target/release/bundle/macos/Agent Fleet.app`, das installierte Ziel unter `~/Applications/Agent Fleet.app`. Ein Build gilt für seine Zielarchitektur. Signierung/Notarisierung am tatsächlichen Artefakt prüfen. Die vorhandene App mit laufenden Anmeldungen erst kontrolliert schließen; ein Fensterstart allein beweist keine erfolgreiche native Oberfläche. Eine reine Remote-App benötigt keine lokalen Provider-Logins.

## Windows: native CLI und Tauri-App

Zum Bauen Rust/MSVC und Git verwenden; für die App zusätzlich Node.js 24 sowie C++-Buildwerkzeuge und WebView2 nach den offiziellen Tauri-Voraussetzungen.

```powershell
cargo build -p fleet-cli --release --locked
.\scripts\install_native.ps1
cd desktop
npm ci
npm run tauri build
```

Der Installer gibt den CLI-Zielpfad unter `%LOCALAPPDATA%\AgentFleet\bin` aus. Mit `-Replace` behält er die vorige EXE als Backup. Den Ordner zum Benutzer-PATH hinzufügen oder den absoluten Pfad verwenden. Desktop-Installer aus `target\release\bundle` installieren. Skills nach Vergleich in beide persönlichen Agentenverzeichnisse übernehmen.

Native Windows-Builds und die Oberfläche tatsächlich auf Windows prüfen; Mac-, Browser- und Cross-Compile-Prüfungen getrennt ausweisen. Alte `.pyz`-/`.pyzw`-Downloads bleiben Python-Versionen und sind keine nativen 0.5-Artefakte. Eine WSL-Installation hat ihren eigenen Linux-Pool; der native Desktop ist ein separater Client.

## Linux-Pool über SSH

Den vom Nutzer gewählten SSH-Alias bzw. `user@host` verwenden. Mit geprüftem Host-Key und Schlüsselzugang verbinden; der Client arbeitet mit `BatchMode=yes`, `StrictHostKeyChecking=yes`, ohne Agent-Forwarding. Einen unbekannten Host-Key erst auf vertrauenswürdigem Weg prüfen. Existierende Dienste und Provider-Sitzungen inventarisieren; für diesen Pool einen eigenen Unix-Benutzer verwenden, wenn das gewünscht bzw. bereits eingerichtet ist.

Die native Rust-CLI und benötigte Provider auf Linux installieren. Mit `cargo build -p fleet-cli --release --locked` im berechtigten Server-Checkout bauen oder ein geprüftes Linux-Artefakt für genau Architektur und libc des Servers übertragen. Eine Mac-/Windows-Binärdatei ist kein Linux-Paket. Unter `~/.local/bin/agent-fleet` ausführbar installieren. Ein bestehender Python-Server kann während einer gestuften Migration über RPC v1 weiterlaufen; ein Server-Upgrade erfolgt erst nach Prüfung der laufenden Queue und separat vom Client-Update. Danach mit demselben Benutzer:

```sh
agent-fleet init
agent-fleet doctor
agent-fleet workspace add projekt --path /absoluter/bestehender/server-projektpfad
agent-fleet service --exec /absoluter/pfad/agent-fleet
```

Nur tatsächlich vorhandene, vom Nutzer gewählte Projektverzeichnisse registrieren; lokale Client-Dateien werden nicht übertragen. `service` erzeugt nur den Unit-Text. Nach Prüfung als `~/.config/systemd/user/agent-fleet.service` speichern und diesen eigenen User-Dienst aktivieren. Eine bereits existierende Unit vergleichen und erhalten, statt blind umzuleiten. Linger mit `loginctl show-user <benutzer> -p Linger` prüfen; ein Administrator kann `loginctl enable-linger <benutzer>` setzen, falls noch erforderlich. Ohne systemd einen unabhängigen Supervisor oder bewusst offen gehaltenen Worker verwenden; keinen dauerhaften Betrieb aus einer kurzlebigen SSH-Sitzung behaupten.

Client-App: **Remote → Verbindung hinzufügen**, Name und SSH-Alias. Die Discovery prüft das installierte Executable, den Pool-Pfad und Login-Unterstützung. Anschließend öffnen und Worker-/Account-Stand lesen. Alternativ explizit:

```sh
agent-fleet remote add zentral --host SSH_ALIAS --command /absoluter/pfad/agent-fleet --server-home /absoluter/poolpfad
agent-fleet remote test zentral
agent-fleet --remote zentral status
```

Pool-Pfad muss genau dem Worker entsprechen. Vorhandene passende Verbindungen wiederverwenden; abweichende nicht still ersetzen. Unter Windows dieselben CLI-Argumente mit der installierten `agent-fleet.exe` verwenden.

Ein bestehender nativer Server-Account kann auf Wunsch mit `profile add <name> --provider codex --binary <absoluter-cli-pfad> --auth-home <bestehendes-verzeichnis>` registriert werden. Das ist eine lokale Server-Administration, kein RPC. Vor Aktivierung native Anmeldung verifizieren. Das externe Verzeichnis wird nicht kopiert oder umgechmodet; andere native Prozesse teilen die Account-Sitzung und beachten die Broker-Sperre nicht. Neue zusätzliche Abos bevorzugt in getrennten Profilen anmelden.

## Worker und Abschluss

`init` erzeugt deaktivierte Profile, keine Logins. Vor Aufträgen die Anmeldung abschließen. Für lokale CLI-Aufträge `agent-fleet work` in einem unabhängigen dauerhaften Prozess/Terminal starten und dessen Lebensdauer erklären; `work --drain` wartet ausgeschöpfte Quoten nicht dauerhaft ab. Auf Linux den installierten Dienst nutzen. Reine lokale Kontingentanzeige braucht keinen Worker.

Nach Installation `--version` und tatsächliches Laden der App prüfen. Native UI-Prüfung auf Mac beweist keine Windows-Abnahme. Bestehende Profile, Queue und übrige Dienste bleiben erhalten.
