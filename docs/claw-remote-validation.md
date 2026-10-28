# claw-remote: Einrichtung und drei Prüfschleifen

Stand: 28.10.2026. Autorisiert: unbeaufsichtigte Einrichtung, Tests und Korrekturen durch Johannes. Spec #3; Tickets #4–#7. Gewählte Testgrenzen: öffentliche CLI/RPC und tatsächliche native Desktop-Aktionen.

## Einrichtung

- Ziel ist der bereits konfigurierte und live geprüfte SSH-Alias `claw-remote`, Benutzer `clawadmin`, Linux x86_64 / Python 3.14.4. Keine neue SSH-Vertrauensregel, kein neuer Netzwerkport.
- CLI: `~/.local/bin/agent-fleet`. Pool: `~/.local/share/agent-pool`. User-Dienst: `agent-fleet.service`, aktiviert und laufend. Linger war bereits aktiv.
- Workspace `validation`: `~/projects/agent-fleet-validation`; enthält ausschließlich die eigens angelegte Abnahmedatei.
- Client-Verbindung `claw-remote` ist im lokalen Mac-Pool gespeichert. In der App **Remote → claw-remote** öffnen.
- `server-codex` verwendet den bestehenden nativen Login auf demselben Server über explizites `--auth-home`. Rechte des vorhandenen Verzeichnisses blieben 0755; keine Credentials kopiert. Profil ist aktiviert, reale Metadaten und Wochenkontingent sind lesbar. Ein vom Anbieter nicht gemeldetes 5-Stunden-Fenster bleibt unbekannt.
- `server-claude` verwendet eine separat unter `~/.local/share/agent-fleet-tools` installierte CLI 2.1.312. Die bisherige globale CLI 2.1.193 und laufende Sitzungen bleiben bestehen. Browser-Link und Code-Eingabestatus sowie Abbruch sind auf Linux geprüft; ein neuer echter Claude-Login braucht noch Browser-Zustimmung.
- Die vorbereiteten `codex-1` bis `codex-3` und `claude-1` bleiben deaktiviert. Noch keine weiteren Abos angemeldet. Für Claude das vorbereitete Profil `server-claude` in **Alle Profile anzeigen** wählen und dort anmelden.
- Vorhandene OpenClaw- und VoxSTT-Dienste wurden vor und nach der Einrichtung als aktiv geprüft und nicht neu gestartet.

## Schleife 1: Nutzerabläufe

Echter Mac-Desktop: Lokal/Remote-Menü, Verbindung über automatische Discovery, Konten laden, Codex-Filter, Suche, Details und Zurück. Keine modalen Auftragsfenster. Echtes Codex-Gerätelogin aus der UI auf Linux gestartet und beim Zurückgehen abgebrochen. Echtes Claude-Gerät bestätigt den Browser-/Code-Status und Abbruch, ohne neue Zustimmung vorzutäuschen.

Realer Subscription-Auftrag `3e700bf6dd774f24a3a4ef3998b4517d`, Profil `server-codex`, einmal ausgeführt, read-only, 90 Sekunden Timeout. Bericht:

```text
FLEET-REMOTE-20261028
42
```

Der Auftrag las die dedizierte Serverdatei; er wurde nach Ende der sendenden SSH-Verbindung vom unabhängigen Worker abgeschlossen.

Gefunden und test-first behoben: Das endungslose installierte Archiv startete seinen Login-Worker fälschlich als nicht installiertes Python-Modul. Hintergrund- und Abbruchprozesse erkennen nun ZIP-Archive am Inhalt. systemd-Anmeldungen übernehmen den expliziten SSH-Suchpfad; Dienste und Provider-Auflösung berücksichtigen die üblichen privaten npm-Binärpfade.

## Schleife 2: Fehler gezielt provozieren

Ausschließlich in einem automatisch erzeugten, danach entfernten Test-Pool auf demselben Host, mit kontrollierter Provider-CLI ohne Inferenz oder Credentials:

- Fünf ungültige/verbotene RPC-Varianten abgelehnt.
- 16 gleichzeitige identische Übermittlungen ergeben genau einen Auftrag; anderer Inhalt unter demselben Schlüssel abgelehnt.
- Unicode und Shell-Ausdrücke unverändert im Bericht, keine Ausführung des Shell-Payloads.
- Nach Ablauf des kurzen Limits blockiert das beobachtete Wochenlimit weiterhin; nach frischer freier Beobachtung genau eine Ausführung. Keine echten Quoten manipuliert.
- Wartenden Auftrag abgebrochen. Worker während eines nativen Testprozesses per SIGTERM beendet: Kindprozess beendet, Auftrag `needs_review`, kein automatischer Replay nach Neustart.
- Installierten Login-Prozess gestartet/abgebrochen; nativer Kindprozess danach beendet.
- In der echten UI: nicht erreichbarer SSH-Host, Rückkehr zum funktionierenden Host, zwölf schnelle Kontextwechsel und verspätete Antworten ohne Tk-Fehler und ohne Umbenennung alter Antworten. Verzögerung wird an der Transportgrenze injiziert; UI und Threading bleiben echt.

Gefunden und test-first behoben: ZIP-CLI gab bei Fehlern und wartenden Aufträgen stets Exit 0 zurück. Der Builder erzeugt jetzt einen expliziten `SystemExit(main())`; Tests prüfen 0/1/2. Ein verschwundener angehängter Account blockiert nicht mehr die gesamte Status-Aktualisierung. Verbundene Accounts ohne gemeldete E-Mail tragen jetzt „Verbunden“ statt „Nicht angemeldet“.

## Schleife 3: Performance und Abnahme

Vorläufige Messung nach den wesentlichen Korrekturen:

| Prüfung | Ergebnis | Ziel |
| --- | --- | --- |
| 20 echte SSH-Statusabfragen | Median 644 ms, p95 785 ms, max. 797 ms | p95 < 3 s |
| 100 kontrollierte native Aufträge | 18,84 s, 5,31/s, genau 100 eindeutige Ausführungen | keine Verluste/Duplikate |
| Tk-Eventloop bei 2 s Transportverzögerung | p95 31 ms, max. 36 ms | p95 < 100 ms, max. < 500 ms |

Die Lastwerte messen Broker, Queue und native Testprozesse. Sie sind keine Inferenzgeschwindigkeit echter Modelle. Abschließende Werte und Paketnachweise stehen in `claw-remote-validation.json`.

## Wiederholen

`tests/real-host/server_checks.py` wird mit dem Pfad des installierten Archivs und `tests/real-host/native_fixture.py` auf dem ausdrücklich ausgewählten Host ausgeführt. Es erzeugt private temporäre Testdaten unter `~/.local/share/agent-fleet-validation` und entfernt seinen Pool nach Abschluss. Bestehenden Pool und echte Accounts verwendet es nicht.

```sh
python3 server_checks.py "$HOME/.local/bin/agent-fleet" native_fixture.py
```

Auf dem Mac mit einem Python inklusive Tk:

```sh
python scripts/test_real_host_desktop.py --remote claw-remote --output /tmp/fleet-gui.json --screenshot /tmp/fleet-overview.png
```

Dieser explizite UI-Test verwendet reale Statusdaten und startet/annulliert einen Geräte-Login im vorbereiteten Profil `codex-1`. Er führt keine Provider-Zustimmung aus und veröffentlicht keine Login-URLs/-Codes. Die erzeugte Verbindungskonfiguration liegt nur im temporären Client-Verzeichnis.

## Betrieb und Rücknahme

```sh
agent-fleet --remote claw-remote status
agent-fleet --remote claw-remote job list
ssh claw-remote 'systemctl --user status agent-fleet --no-pager'
```

Für normale Agentenaufträge existiert der Test-Workspace `validation`. Eigene produktive Projekte vorab auf dem Server separat registrieren. Dateien werden nicht vom Mac synchronisiert.

Rücknahme der neuen Einrichtung: ausschließlich `agent-fleet.service` stoppen/deaktivieren und die Client-Verbindung mit `agent-fleet remote remove claw-remote` entfernen. Pool und Logins zunächst erhalten; angehängtes `~/.codex` gehört zur bestehenden Serverinstallation und wird nicht gelöscht. Keine Serverdienste oder Credentials automatisch bereinigen.

## Grenzen

Keine vollständige neue Browser-Zustimmung für zusätzliche Konten; bestehender Server-Codex ist real nachgewiesen. Kein nativer Windows-Desktop auf diesem Mac abgenommen. GitHub Actions hat eine bekannte separate Abrechnungssperre; lokale und reale Linux-Tests werden unabhängig berichtet.
