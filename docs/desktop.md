# Agent Pool Desktop — 0.2.0

Ein lokales Fenster für alle verbundenen Accounts und ihre gemeldeten Nutzungslimits.

## Mac

Das Mac-Paket aus den [Downloads](https://github.com/the-fin-at/agent-pool/releases/latest) entpacken und `Agent Pool.app` in den persönlichen Programme-Ordner kopieren:

```sh
open "$HOME/Applications/Agent Pool.app"
```

Alternativ mit dem aktualisierten CLI-Befehl:

```sh
agent-pool desktop
```

Das Mac-Paket enthält Python und Tk; dafür ist kein Python-Setup nötig. Für echte Account-Abfragen muss die native Codex-CLI auf dem Rechner vorhanden sein. Die App findet persönliche CLI-Installationen auch beim Start aus dem Finder. Die gebaute Version ist für Apple Silicon; andere Architekturen benötigen einen eigenen Build. Der lokale Build ist ad hoc signiert, nicht als öffentliche Veröffentlichung notarisiert.

## Windows

Aktuell steht das portable `.pyzw`-Paket zur Verfügung. Der native EXE-Build wurde von GitHub vor Runner-Start wegen Kontoabrechnung/Ausgabenlimit blockiert; es wird kein erfolgreicher Windows-Build behauptet. [CI-Nachweis](validation.md#ci-und-builds).

Das portable Paket `dist/Agent-Pool-Windows-Portable.zip` enthält `Agent Pool.pyzw`, das CLI-Paket und diese Anleitung. Voraussetzung ist Python 3.11+ **mit Tcl/Tk**, wie im regulären Python-Windows-Installer angeboten, sowie die native Codex-CLI für Live-Quoten.

Nach dem Entpacken `Agent Pool.pyzw` doppelklicken. Falls die Dateizuordnung fehlt, aus PowerShell starten:

```powershell
pyw -3 '.\Agent Pool.pyzw'
```

Bei fehlendem `pyw` funktioniert auch `py -3 '.\Agent Pool.pyzw'`; dann bleibt zusätzlich das Terminal sichtbar. Die Account-Logins sind je Maschine lokal; Tokens werden nicht über den gemeinsamen Projektordner übertragen. Für die zusätzlichen Profile auf dem Windows-Rechner einmalig:

```powershell
py -3 '.\agent-pool.pyz' init
py -3 '.\agent-pool.pyz' login codex-2
py -3 '.\agent-pool.pyz' login codex-3
```

Ein eigenständiges Windows-`.exe`-Paket lässt sich **auf Windows** mit dem beiliegenden Projekt bauen. [PyInstaller baut native Pakete jeweils auf dem Zielbetriebssystem](https://www.pyinstaller.org/en/stable/):

```powershell
py -3 -m venv .venv-desktop
.\.venv-desktop\Scripts\python -m pip install -r requirements-desktop-build.txt
.\.venv-desktop\Scripts\python scripts/build_desktop.py
```

Ergebnis: `dist\windows\Agent Pool\Agent Pool.exe` zusammen mit dem `_internal`-Ordner. Den ganzen Ordner weitergeben, nicht nur die EXE. Die manuell startbare GitHub-Actions-Datei `.github/workflows/desktop.yml` bereitet native Builds für Mac und Windows vor, sobald dieses Projekt in einem Repository mit Actions liegt. Der aktuelle Build- und Plattform-Prüfstand steht im [Prüfnachweis](validation.md). Windows-Pakete werden auf einem Windows-Runner gebaut.

## Was angezeigt wird

- E-Mail, Provider und der vom Anbieter gemeldete Tarif.
- Restkontingent in Prozent, Verbrauchsbalken und lokale Reset-Zeitpunkte.
- Alle tatsächlich gemeldeten Quotenfenster, einschließlich zusätzlicher Modell-Buckets. Ein fehlendes Fünf-Stunden-Fenster wird nicht erfunden.
- Den bestehenden nativen Codex-Hauptaccount als Anzeigequelle sowie alle lokal eingerichteten Pool-Profile.
- Der bestehende Hauptaccount dient in der App als Anzeigequelle. Damit wird er nicht automatisch für Pool-Aufträge freigeschaltet.
- Auch pausierte oder nicht angemeldete Profile sind über „Auch unverbundene Profile“ sichtbar. Die Suche filtert nach E-Mail, Profil, Provider und Tarif.

Die App lädt zunächst den letzten lokalen Stand und aktualisiert dann im Hintergrund, automatisch alle 60 Sekunden oder per „Jetzt aktualisieren“ / Cmd-R / Ctrl-R. Sie startet keine Modellaufträge und arbeitet keine Jobs ab. Die Job-Queue wird weiterhin von `agent-pool work` bedient.

Bei fehlgeschlagenen Abfragen bleiben vorherige Werte als letzter bekannter Stand sichtbar. Nach Überschreiten eines gemeldeten Resets zeigt die App „Nicht aktuell“, bis eine neue Beobachtung vorliegt. Ein abgelaufener Timer gilt nicht automatisch als Nachweis für 100 % freies Kontingent. Der Datenstand und Fehler sind je Account erkennbar.

Claude-Quoten stammen weiterhin aus den vom Broker gespeicherten nativen CLI-Ereignissen. Für Claude gibt es in diesem Stand keine zusätzliche private Usage-HTTP-Abfrage; noch fehlende Daten werden als unbekannt angezeigt. Neue Browser-Logins erfolgen weiterhin über die CLI.

## Datenhaltung und Prüfungen

Desktop und CLI teilen sich das lokale `AgentPool`-State-Verzeichnis. Ein neuer SQLite-Cache speichert ausschließlich normalisierte Account-Zuordnung, Tarif, Quoten und Zeitpunkte. Authentifizierung bleibt bei der nativen Provider-CLI. Bei einem erkannten Accountwechsel übernimmt die Anzeige keine alten Kontingente für die neue Identität.

Lokale Tests mit Tk-fähigem Python:

```sh
python -m unittest discover -s tests -v
```

55 Tests bestehen auf dem Mac, einschließlich eines Tests in einem frischen nativen Prozess für die erste Fensterdarstellung. Python-Installationen ohne Tk überspringen die vier GUI-Tests; auf einem System ohne Bildschirm können GUI-Tests ebenfalls übersprungen werden. Die finale Mac-App wird zusätzlich mit echten Account-Metadaten geprüft. Windows bleibt als echte Plattformprüfung offen.
