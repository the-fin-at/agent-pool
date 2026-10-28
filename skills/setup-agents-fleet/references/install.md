# Installation und Verbindung

## Quelle, Version und Bestand

Quellprojekt: https://github.com/the-fin-at/agent-pool (privat). Fehlenden Repository-Zugriff über den berechtigten GitHub-Account lösen; keine Abos oder Zugangsdaten aus anderen Profilen übernehmen. Bestehenden Checkout anhand seiner Git-Remote identifizieren. Einen schmutzigen Checkout erhalten und in einem separaten Checkout bauen. Für einen neuen Checkout:

```sh
git clone https://github.com/the-fin-at/agent-pool.git
cd agent-pool
```

Repository-Anleitungen nach dem Auschecken lesen: `docs/desktop.md`, `docs/remote.md`, bei vorhandenen Profilen auch `docs/overview-login.md`. Installation und CLI-Vertrag am tatsächlichen Quellstand prüfen. Aktuelle native Provider-Installationswege aus den offiziellen Quellen beziehen: https://developers.openai.com/codex/cli und https://code.claude.com/docs/en/setup. Provider werden nur auf dem ausführenden Rechner benötigt. Unter Windows echte EXEs verwenden; CMD/BAT-Shims werden vom Broker abgelehnt.

Bei vorhandener Installation zuerst Executable/App-Version, State-Verzeichnis, laufende Jobs und Dienste feststellen. Bei einem Update CLI/App/Skills sichern, nicht den Pool ersetzen. Während laufender Aufträge den Worker nicht zum Aktualisieren abbrechen. Binaries und App auf derselben Maschine bereitstellen und gezielt austauschen; nach Prüfung nur den eigenen Agent-Fleet-Worker kontrolliert neu starten. Der Installer bricht vor Änderungen ab, wenn ein Ziel existiert; diese Meldung ist kein Anlass zum Löschen von State oder Skills. Neue Skill-Versionen nach Vergleich gezielt kopieren und eigene Anpassungen erhalten.

## Mac: CLI und App

Python 3.11+ und Git verwenden. Für die native App einen verfügbaren Python mit funktionierendem Tcl/Tk auswählen; `import tkinter` allein beweist noch kein lauffähiges Fenster. Erstinstallation:

```sh
python3 scripts/build_zipapp.py
python3 scripts/install_local.py
```

CLI-Ziele sind `~/.local/bin/agent-fleet` und `agent-pool`; Skills werden unter `~/.agents/skills` und `~/.claude/skills` installiert. Für diese Sitzung `~/.local/bin` in PATH nehmen oder den absoluten Executable-Pfad verwenden. Shell-Konfiguration nur gezielt ergänzen, bestehende Einträge erhalten.

Ein zum aktuellen Stand passendes Mac-App-Paket bevorzugen. Falls es fehlt, mit einem Python inklusive Tk in einer Build-Umgebung bauen:

```sh
python3 -m venv .venv-desktop
.venv-desktop/bin/python -m pip install -r requirements-desktop-build.txt
.venv-desktop/bin/python scripts/build_desktop.py
```

`dist/macos/Agent Fleet.app` nach `~/Applications/Agent Fleet.app` installieren. Der Build gilt für die Architektur des Build-Rechners und ist ad hoc signiert, nicht öffentlich notarisiert. Danach öffnen und tatsächlich laden lassen. Die reine Remote-App benötigt dort keine native Codex-/Claude-CLI. Eine vorhandene App mit unbekannten laufenden Sitzungen nicht pauschal beenden.

## Windows: CLI und portable App

Python 3.11+ mit Tcl/Tk, Git und für Remote OpenSSH Client prüfen. Mit `py -3` bauen und installieren:

```powershell
py -3 scripts/build_zipapp.py
py -3 scripts/build_desktop.py --portable-only
py -3 scripts/install_local.py
```

Die installierte CLI liegt unter `%USERPROFILE%\.local\bin\agent-fleet.pyz`. Beispielaufruf:

```powershell
py -3 "$env:USERPROFILE\.local\bin\agent-fleet.pyz" --version
pyw -3 '.\dist\Agent Fleet.pyzw'
```

Das portable Desktop-Archiv an einem dauerhaften Ort behalten; es benötigt Python/Tk. Bei fehlendem `pyw` ist `py -3` möglich. Ein natives EXE-Paket mit PyInstaller ausschließlich auf Windows bauen und vollständig mit seinem `_internal`-Ordner installieren. Kein Download oder Windows-Build-Erfolg ohne tatsächliches Artefakt behaupten. WSL-Ausführung hält Broker, Provider-CLIs und Projekte zusammen in WSL; ein nativer Windows-Desktop ist davon ein separater Client.

## Linux-Pool über SSH

Den vom Nutzer gewählten SSH-Alias bzw. `user@host` verwenden. Mit geprüftem Host-Key und Schlüsselzugang verbinden; der Client arbeitet mit `BatchMode=yes`, `StrictHostKeyChecking=yes`, ohne Agent-Forwarding. Einen unbekannten Host-Key erst auf vertrauenswürdigem Weg prüfen. Existierende Dienste und Provider-Sitzungen inventarisieren; für diesen Pool einen eigenen Unix-Benutzer verwenden, wenn das gewünscht bzw. bereits eingerichtet ist.

Python 3.11+, Agent-Fleet-CLI und benötigte native Provider auf Linux installieren. Entweder im berechtigten Server-Checkout bauen oder das lokal gebaute reine Python-Archiv übertragen. Das Archiv ist portabel; native App-Pakete sind es nicht. Auf Linux unter `~/.local/bin/agent-fleet` ausführbar installieren. Danach mit demselben Benutzer:

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

Pool-Pfad muss genau dem Worker entsprechen. Vorhandene passende Verbindungen wiederverwenden; abweichende nicht still ersetzen. Unter Windows dieselben CLI-Argumente hinter `py -3 <installierte-agent-fleet.pyz>` setzen.

Ein bestehender nativer Server-Account kann auf Wunsch mit `profile add <name> --provider codex --binary <absoluter-cli-pfad> --auth-home <bestehendes-verzeichnis>` registriert werden. Das ist eine lokale Server-Administration, kein RPC. Vor Aktivierung native Anmeldung verifizieren. Das externe Verzeichnis wird nicht kopiert oder umgechmodet; andere native Prozesse teilen die Account-Sitzung und beachten die Broker-Sperre nicht. Neue zusätzliche Abos bevorzugt in getrennten Profilen anmelden.

## Worker und Abschluss

`init` erzeugt deaktivierte Profile, keine Logins. Vor Aufträgen die Anmeldung abschließen. Für lokale CLI-Aufträge `agent-fleet work` in einem unabhängigen dauerhaften Prozess/Terminal starten und dessen Lebensdauer erklären; `work --drain` wartet ausgeschöpfte Quoten nicht dauerhaft ab. Auf Linux den installierten Dienst nutzen. Reine lokale Kontingentanzeige braucht keinen Worker.

Nach Installation `--version` und tatsächliches Laden der App prüfen. Native UI-Prüfung auf Mac beweist keine Windows-Abnahme. Bestehende Profile, Queue und übrige Dienste bleiben erhalten.
