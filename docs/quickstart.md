# Lokal installieren und den ersten Auftrag ausführen

[Übersicht](../README.md) · [Native Desktop-App](desktop.md) · [Migration](rust-migration.md)

Du brauchst Zugriff auf `the-fin-at/agent-pool` sowie die offiziellen nativen Codex-/Claude-CLIs für die Anbieter, die auf diesem Rechner arbeiten sollen. Agent Fleet verwendet deine eigenen Anmeldungen. Ein reiner SSH-Client benötigt nur die Agent-Fleet-CLI und den eingerichteten SSH-Zugang.

## Mac und Linux

Für einen Build aus dem Repository Rust gemäß `rust-toolchain.toml` installieren:

```sh
git clone https://github.com/the-fin-at/agent-pool.git
cd agent-pool
cargo build -p fleet-cli --release --locked
sh scripts/install_native.sh
export PATH="$HOME/.local/bin:$PATH"
agent-fleet doctor
```

Eine bestehende Installation erst vergleichen; `--replace` ersetzt sie mit Backup. Vorhandene Pools, Accounts und Ergebnisse bleiben am bisherigen Ort. `init` ist nur bei einer Ersteinrichtung nötig:

```sh
agent-fleet init
agent-fleet login codex-1
agent-fleet quota refresh codex-1
```

Weitere Profile mit `login codex-2` und `login claude-1` anmelden und im Browser den gewünschten Account wählen. Den Mac-Desktop gemäß [Desktop-Anleitung](desktop.md) bauen. Fertige native Programme brauchen keine Python-, Rust- oder Node-Installation.

## Windows

Für den Build Rust/MSVC installieren; für die App zusätzlich die [Tauri-Voraussetzungen](https://v2.tauri.app/start/prerequisites/#windows).

```powershell
git clone https://github.com/the-fin-at/agent-pool.git
cd agent-pool
cargo build -p fleet-cli --release --locked
.\scripts\install_native.ps1
```

Den ausgegebenen `bin`-Ordner zum Benutzer-PATH hinzufügen. Bei vorhandener Installation nach Prüfung `-Replace` verwenden. Danach gelten dieselben `agent-fleet`-Befehle wie auf dem Mac. Native Provider-EXEs verwenden; CMD-/BAT-Shims werden nicht als Provider gestartet. Desktop-Installer mit `npm ci` und `npm run tauri build` in `desktop/` bauen. Eine tatsächlich ausgeführte Windows-Abnahme wird im [Migrationsnachweis](rust-migration.md) separat ausgewiesen.

## Ersten Auftrag ausführen

Im vorhandenen Projektverzeichnis:

```sh
agent-fleet run --provider codex --cwd . --prompt "Beschreibe kurz dieses Projekt. Ändere keine Dateien."
```

Ohne `--profile` wählt der Worker selbst ein verfügbares Profil desselben Anbieters. Er berücksichtigt alle passenden 5-Stunden-, Wochen- und Modelllimits. Ein ausdrücklich gewähltes Profil bleibt gebunden. `succeeded` enthält den Bericht; `waiting` ist noch offen, `failed` oder `needs_review` ist kein Erfolg.

Für längere Aufgaben einen Worker in einem Terminal laufen lassen:

```sh
agent-fleet work
```

In einem zweiten Terminal:

```sh
agent-fleet job submit --provider codex --cwd . --prompt-file task.txt --key erster-test-001
agent-fleet job get <job-id>
```

In `task.txt` Ziel, betroffene Dateien und Abnahmekriterien angeben. Dateiänderungen erfordern ausdrücklich `--allow-edits`. Einen unsicher zugestellten Auftrag mit demselben Schlüssel und Inhalt erneut senden; dadurch entsteht kein zweiter Auftrag. Der Desktop zeigt Accounts und Anmeldungen, startet aber keinen Worker.

## Wenn etwas nicht klappt

| Beobachtung | Nächster Schritt |
|---|---|
| Provider fehlt | Native CLI installieren, dann `doctor`. |
| Account nicht verbunden | `login <profil>` abschließen. |
| Quoten fehlen | `quota refresh <profil>`; Claude benötigt gespeicherte CLI-Ereignisse oder eine manuelle Beobachtung. |
| Auftrag wartet | `quota show` prüfen und den Worker laufen lassen. Ein unbekannter Reset bleibt gesperrt. |
| `needs_review` | Ergebnis, Arbeitsverzeichnis und Restprozesse prüfen; erst danach gezielt erneut freigeben. |
| Anzeige veraltet | Zeitstempel und Fehler in den Account-Details prüfen, aktualisieren. |

Native Account-Verzeichnisse und Credentials bleiben auf dem jeweiligen Rechner. Sie gehören nicht ins Repository oder in synchronisierte Projektordner.
