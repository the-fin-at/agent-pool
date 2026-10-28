# Agent Fleet Desktop · 0.4.0

Ein Fenster für alle verbundenen Accounts: im THE-FIN-Design mit Seitenleiste, Kontingentkreisen und Wochenbalken. Lokal und für konfigurierte Linux-Server.

Die 0.4-Ansicht wird aus dem aktuellen Quellstand gebaut. Ältere Release-Pakete enthalten die neue Kontextnavigation und integrierte Anmeldung noch nicht.

## Mac

Den aktuellen Quellstand mit einem Tk-fähigen Python 3.11+ bauen und das Ergebnis in den persönlichen Programme-Ordner kopieren:

```sh
python3 -m pip install -r requirements-desktop-build.txt
python3 scripts/build_desktop.py
# Ergebnis: dist/macos/Agent Fleet.app
```

Anschließend starten:

```sh
open "$HOME/Applications/Agent Fleet.app"
```

Alternativ mit dem aktualisierten CLI-Befehl:

```sh
agent-fleet desktop
```

Das Mac-Paket enthält Python und Tk; dafür ist kein Python-Setup nötig. Für echte Account-Abfragen muss die native Codex-CLI auf dem Rechner vorhanden sein. Die App findet persönliche CLI-Installationen auch beim Start aus dem Finder. Die gebaute Version ist für Apple Silicon; andere Architekturen benötigen einen eigenen Build. Der lokale Build ist ad hoc signiert, nicht als öffentliche Veröffentlichung notarisiert.

## Windows

Aktuell steht das portable `.pyzw`-Paket zur Verfügung. Der native EXE-Build wurde von GitHub vor Runner-Start wegen Kontoabrechnung/Ausgabenlimit blockiert; es wird kein erfolgreicher Windows-Build behauptet. [CI-Nachweis](validation.md#ci-und-builds).

Das portable Paket `dist/Agent-Fleet-Windows-Portable.zip` enthält `Agent Fleet.pyzw`, das CLI-Paket und diese Anleitung. Voraussetzung ist Python 3.11+ **mit Tcl/Tk**, wie im regulären Python-Windows-Installer angeboten, sowie die native Codex-CLI für Live-Quoten.

Nach dem Entpacken `Agent Fleet.pyzw` doppelklicken. Falls die Dateizuordnung fehlt, aus PowerShell starten:

```powershell
pyw -3 '.\Agent Fleet.pyzw'
```

Bei fehlendem `pyw` funktioniert auch `py -3 '.\Agent Fleet.pyzw'`; dann bleibt zusätzlich das Terminal sichtbar. Die Account-Logins sind je Maschine lokal; Tokens werden nicht über den gemeinsamen Projektordner übertragen. Für die zusätzlichen Profile auf dem Windows-Rechner einmalig:

```powershell
py -3 '.\agent-fleet.pyz' init
py -3 '.\agent-fleet.pyz' login codex-2
py -3 '.\agent-fleet.pyz' login codex-3
```

Ein eigenständiges Windows-`.exe`-Paket lässt sich **auf Windows** mit dem beiliegenden Projekt bauen. [PyInstaller baut native Pakete jeweils auf dem Zielbetriebssystem](https://www.pyinstaller.org/en/stable/):

```powershell
py -3 -m venv .venv-desktop
.\.venv-desktop\Scripts\python -m pip install -r requirements-desktop-build.txt
.\.venv-desktop\Scripts\python scripts/build_desktop.py
```

Ergebnis: `dist\windows\Agent Fleet\Agent Fleet.exe` zusammen mit dem `_internal`-Ordner. Den ganzen Ordner weitergeben, nicht nur die EXE. Die manuell startbare GitHub-Actions-Datei `.github/workflows/desktop.yml` bereitet native Builds für Mac und Windows vor, sobald dieses Projekt in einem Repository mit Actions liegt. Der aktuelle Build- und Plattform-Prüfstand steht im [Prüfnachweis](validation.md). Windows-Pakete werden auf einem Windows-Runner gebaut.

## Was angezeigt wird

- E-Mail, Provider und der vom Anbieter gemeldete Tarif.
- Große Kreise für das freie Kontingent im 5-Stunden-Fenster; die Wochenbalken zeigen ebenfalls den freien Anteil. Das Fenster ist keine verbleibende Rechenzeit.
- Filter für alle Accounts, Codex oder Claude. Die Suche ergänzt den gewählten Anbieterfilter.
- Drei, zwei oder eine Spalte je Fensterbreite; unter 880 px wandert die Navigation nach oben.
- Eingebettete Albert-Sans-Schriften und originale THE-FIN-Markenassets. Es sind keine separat installierten Fonts oder persönlichen Asset-Pfade nötig.
- Alle tatsächlich gemeldeten Quotenfenster, einschließlich zusätzlicher Modell-Buckets. Ein fehlendes Fünf-Stunden-Fenster wird nicht erfunden.
- Den bestehenden nativen Codex-Hauptaccount als Anzeigequelle sowie alle lokal eingerichteten Profile.
- Der bestehende Hauptaccount dient in der App als Anzeigequelle. Damit wird er nicht automatisch für Aufträge freigeschaltet.
- Auch pausierte oder nicht angemeldete Profile sind über „Alle Profile anzeigen“ sichtbar. Die Suche filtert nach E-Mail, Profil, Provider und Tarif.

Die App lädt zunächst den letzten lokalen Stand und aktualisiert dann im Hintergrund, automatisch alle 60 Sekunden oder per „Aktualisieren“ / Cmd-R / Ctrl-R. Oben links zwischen Lokal und Remote wechseln. Remote zeigt zunächst die Verbindungen, dann die Accounts des gewählten Servers. Verbindungen und neue Accounts werden in integrierten Ansichten hinzugefügt; der SSH-Schlüsselzugang wird vorher eingerichtet. Die Job-Queue wird von einem separaten `agent-fleet work` bedient; das Schließen des Fensters beendet keinen Remote-Worker.

Bei fehlgeschlagenen Abfragen bleiben vorherige Werte als letzter bekannter Stand sichtbar. Nach Überschreiten eines gemeldeten Resets zeigt die App „Nicht aktuell“, bis eine neue Beobachtung vorliegt. Ein abgelaufener Timer gilt nicht automatisch als Nachweis für 100 % freies Kontingent. Der Datenstand und Fehler sind je Account erkennbar.

Claude-Quoten stammen weiterhin aus den vom Broker gespeicherten nativen CLI-Ereignissen. Für Claude gibt es in diesem Stand keine zusätzliche private Usage-HTTP-Abfrage; noch fehlende Daten werden als unbekannt angezeigt. Neue Browser-Logins können direkt aus der App gestartet werden; die offizielle native CLI verarbeitet die Anmeldung auf dem Zielrechner.

## Datenhaltung und Prüfungen

Desktop und CLI teilen sich das lokale `AgentPool`-State-Verzeichnis. Ein neuer SQLite-Cache speichert ausschließlich normalisierte Account-Zuordnung, Tarif, Quoten und Zeitpunkte. Authentifizierung bleibt bei der nativen Provider-CLI. Bei einem erkannten Accountwechsel übernimmt die Anzeige keine alten Kontingente für die neue Identität.

Lokale Tests mit Tk-fähigem Python:

```sh
python -m unittest discover -s tests -v
```

Die Tests prüfen unter anderem die erste Fensterdarstellung in einem frischen nativen Prozess. Python-Installationen ohne Tk überspringen GUI-Tests; auf einem System ohne Bildschirm können GUI-Tests ebenfalls übersprungen werden. Die finale Mac-App wird zusätzlich mit echten Account-Metadaten geprüft. Windows bleibt als echte Plattformprüfung offen.


## Übersicht und Login ab 0.4

Das Dashboard wechselt oben zwischen Lokal und Remote. Unter Remote erscheint zunächst die Verbindungsübersicht; anschließend die Accounts des gewählten Servers. Account-Details, Verbindungen und Browser-Login sind integrierte Ansichten im Hauptfenster. Der bisherige Auftragsdialog gehört nicht mehr zur Desktop-Oberfläche; Agenten verwenden weiterhin die CLI. Der genaue Ablauf und die realen Nachweise stehen unter [Übersicht und Login](overview-login.md).
