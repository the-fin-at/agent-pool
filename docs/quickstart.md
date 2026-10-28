# Lokal installieren und den ersten Auftrag ausführen

[Übersicht](../README.md) · [Downloads](https://github.com/the-fin-at/agent-pool/releases/latest)

Du brauchst Zugriff auf das private Repository `the-fin-at/agent-pool`, Python 3.11+ und eine aktuelle native Codex-CLI. Für Claude-Aufträge zusätzlich Claude Code installieren. Getestete lokale Provider-Versionen: Codex 0.161.0 und Claude Code 2.1.312. Der Broker stellt keine Accounts bereit; du meldest deine eigenen berechtigten Accounts über die Provider an.

## Mac

1. Projekt holen und das CLI-Paket bauen:

   ```sh
   git clone https://github.com/the-fin-at/agent-pool.git
   cd agent-pool
   python3 scripts/build_zipapp.py
   python3 scripts/install_local.py
   export PATH="$HOME/.local/bin:$PATH"
   ```

   Der Installer kopiert Programm und Skill in deine persönlichen Verzeichnisse und überschreibt vorhandene Ziele nicht. Die PATH-Zeile gilt für das aktuelle Terminal; bei Bedarf in die eigene Shell-Konfiguration übernehmen.

2. Profile vorbereiten und deinen ersten Account verbinden:

   ```sh
   agent-fleet init
   agent-fleet login codex-1
   agent-fleet quota refresh codex-1
   agent-fleet doctor
   ```

3. Weitere eigene Accounts verbinden. Für jeden Browser-Login den gewünschten Account wählen:

   ```sh
   agent-fleet login codex-2
   agent-fleet login codex-3
   # Optional, wenn Claude verwendet wird:
   agent-fleet login claude-1
   ```

4. Einen ersten Leseauftrag in einem vorhandenen Projektordner ausführen:

   ```sh
   agent-fleet run --provider codex --cwd /pfad/zum/projekt --prompt "Beschreibe kurz, was dieses Projekt macht. Ändere keine Dateien."
   ```

   Erfolg: Ausgabe mit `status: succeeded` und einem Bericht in `result`. `waiting` ist ein noch offener Auftrag; `failed` oder `needs_review` ist kein erfolgreicher Abschluss.

5. Optional den Desktop aus den [Downloads](https://github.com/the-fin-at/agent-pool/releases/latest) installieren: Mac-ZIP entpacken, `Agent Fleet.app` nach `~/Applications` kopieren und öffnen. Die App zeigt die Accounts und aktualisiert alle 60 Sekunden. Die lokale `.app` ist ad hoc signiert; eine öffentliche Apple-Notarisierung ist nicht enthalten.

## Windows

1. Projekt holen und das CLI-Paket bauen:

   ```powershell
   git clone https://github.com/the-fin-at/agent-pool.git
   cd agent-pool
   py -3 scripts/build_zipapp.py
   ```

2. Profile vorbereiten und einen eigenen Account verbinden:

   ```powershell
   py -3 dist/agent-fleet.pyz init
   py -3 dist/agent-fleet.pyz login codex-1
   py -3 dist/agent-fleet.pyz quota refresh codex-1
   py -3 dist/agent-fleet.pyz doctor
   ```

   Weitere Profile mit `login codex-2` und `login codex-3` anmelden. Für Claude optional `login claude-1`. Native Provider-EXEs verwenden; npm-CMD-/BAT-Shims funktionieren nicht. Alternativ CLI, Broker und Projekte gemeinsam unter WSL betreiben; der native Desktop läuft getrennt unter Windows.

3. Ersten Leseauftrag ausführen:

   ```powershell
   py -3 dist/agent-fleet.pyz run --provider codex --cwd C:\work\projekt --prompt "Beschreibe kurz, was dieses Projekt macht. Ändere keine Dateien."
   ```

4. Desktop aus den [Downloads](https://github.com/the-fin-at/agent-pool/releases/latest) vollständig entpacken. Bei einem nativen Paket `Agent Fleet.exe` starten und den `_internal`-Ordner daneben behalten. Alternativ das portable Paket nutzen:

   ```powershell
   pyw -3 '.\Agent Fleet.pyzw'
   ```

   Die portable Variante benötigt Python mit Tcl/Tk. Bei fehlender `pyw`-Dateizuordnung funktioniert auch `py -3`, dann mit sichtbarem Terminal.

5. Den Skill installieren:

   ```powershell
   py -3 scripts/install_local.py
   ```

   Der Installer legt das Paket unter `%USERPROFILE%\.local\bin\agent-fleet.pyz` ab und kopiert den Skill in die persönlichen Verzeichnisse. Im Skill bzw. Agentenaufruf die tatsächlich vorhandene `.pyz` verwenden, beispielsweise `py -3 C:\pfad\zu\agent-fleet.pyz`.

## Längere Aufgaben über einen Worker

Ein Terminal offenlassen:

```sh
agent-fleet work
```

In einem zweiten Terminal die Aufgabe einreichen:

```sh
agent-fleet job submit --provider codex --cwd /pfad/zum/projekt --prompt-file task.txt --key erster-test-001
agent-fleet job get <job-id>
```

Unter Windows stattdessen `py -3 dist/agent-fleet.pyz work` bzw. `py -3 dist/agent-fleet.pyz job ...` verwenden.

Schreibe in `task.txt`: Ziel, betroffene Dateien, Abnahmekriterien und das gewünschte Berichtsformat. Bei Dateiänderungen ausdrücklich `--allow-edits` ergänzen. Änderungen prüfen, bevor sie übernommen werden. Der Desktop ist ein Monitor; für Warteschlange und automatische Wiederaufnahme muss `work` laufen.

## Wenn etwas nicht klappt

| Beobachtung | Nächster Schritt |
|---|---|
| Repository nicht erreichbar | Mit dem GitHub-Account anmelden, der Zugriff auf `the-fin-at` hat. |
| Provider-Binary fehlt | Native Codex-/Claude-CLI installieren, dann `doctor` wiederholen. |
| Account nicht verbunden | `login <profil>` starten und den Browser-Login abschließen. |
| Quoten fehlen | `quota refresh <profil>`; bei Claude sind CLI-Ereignisse oder eine manuelle Beobachtung nötig. |
| Job wartet | `quota show` prüfen. Bei bekanntem Limit auf den Reset warten und den Worker laufen lassen. |
| `needs_review` | Arbeitsverzeichnis und mögliche Kindprozesse prüfen; erst danach `job retry <id>`. |
| Desktop zeigt alten Stand | Manuell aktualisieren; Fehler und Zeitstempel in den Account-Details prüfen. |

Die Profile und deren Credentials gehören auf die jeweilige Maschine. Sie werden weder aus dem Repository geladen noch zwischen Nutzern synchronisiert.
