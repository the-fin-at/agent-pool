# Prüfstand · 0.2.0

Stand: 28. Oktober 2026. Lokale Tests, Paketprüfungen und CI-Ergebnisse werden getrennt festgehalten.

## Lokal auf macOS

- Python 3.12.14, Tk 9.0.4, Apple Silicon.
- **55 Tests erfolgreich**, einschließlich vier nativer Fenster-Tests. Ein Lauf ohne Tk überspringt die GUI-Tests und ist daher kein gleichwertiger Desktop-Nachweis.
- Prozess-Tests prüfen tatsächliche Betriebssystemgrenzen: einreichendes CLI, Worker und kontrollierter Provider-Ersatzprozess. Sie ersetzen keinen echten Modellauftrag.
- Abgedeckt: konkurrierende idempotente Einreichungen, OS-Workersperre, Persistenz, explizite Profilbindung, Provider-Trennung, Quoten-Buckets, spätester ausgeschöpfter Reset, unbekannte Reset-Zeiten, tatsächliche Subprozess-Timeouts und vorsichtiger Wiederanlauf.
- Desktop-Tests prüfen Suche, Filter, Bedienbarkeit während blockierter Abfragen und Fehlerbehandlung. Der First-Window-Test startet einen frischen Prozess; er reproduzierte zunächst einen 200-Pixel-Clippingfehler und besteht nach der Layout-Korrektur.

## Tatsächliches Mac-App-Paket

Die mit PyInstaller gebaute Apple-Silicon-App wurde als eigener Prozess gestartet. Der [normalisierte Bericht](desktop-macos-smoke.json) zeigt:

- Fenstergröße **1100 × 790 Pixel**.
- Abgeschlossene Metadaten-Aktualisierung.
- Drei verbundene Accounts, insgesamt fünf vom Anbieter gemeldete Quotenfenster und keine Abfragefehler.
- Zwei unverbundene Profile weiterhin als solche erkennbar.

`codesign --verify --deep --strict` erfolgreich. Ad-hoc-Signatur, keine öffentliche Apple-Notarisierung. Die abschließende Prüfung der Fenstergröße und Daten erfolgte im App-Prozess; eine externe Bildschirmaufnahme stand nach der Layout-Korrektur nicht mehr zur Verfügung.

## Native Provider

- Codex CLI **0.161.0**: dokumentierten App-Server-Handshake und `account/rateLimits/read` geprüft, zunächst mit leerem temporärem Profil und anschließend mit angemeldeten Profilen. Die echten Account- und Quotenabfragen wurden erfolgreich ausgeführt; dafür wurde kein Modellturn gestartet.
- Claude Code **2.1.312**: Print-/JSONL-/Restricted-/Werkzeugoptionen und strukturierten Fehlerpfad mit leerem temporärem Profil geprüft. `subtype:success` zusammen mit `is_error:true` wird korrekt als Fehler behandelt.
- Der Skill besteht den offiziellen Skill-Validator. Die dafür verwendete YAML-Bibliothek ist keine Laufzeitabhängigkeit des Programms.

## CI und Builds

Die Testmatrix in `.github/workflows/test.yml` umfasst macOS, Windows und Linux mit Python 3.11/3.14. Der manuell startbare Workflow `desktop-build` baut native Desktop-Pakete mit Python 3.12 auf Mac und Windows.

Die ersten Läufe am 28. Oktober 2026 wurden **vor dem Start der eigentlichen Jobs durch GitHub blockiert**:

- [Testmatrix](https://github.com/the-fin-at/agent-pool/actions/runs/40681076817)
- [Native Desktop-Builds](https://github.com/the-fin-at/agent-pool/actions/runs/40681071080)

Die Windows-Build- und Test-Annotations melden denselben Grund: fehlgeschlagene Kontozahlungen oder ein zu niedriges Ausgabenlimit. Es wurden keine Build-/Test-Schritte ausgeführt. Daraus folgt kein Code-Testergebnis; die CI ist aktuell nicht erfolgreich verifiziert. Kontoabrechnung und Limits wurden nicht verändert.

Das Release enthält deshalb die lokal geprüfte Apple-Silicon-App und das portable Windows-Archiv mit Python-/Tk-Voraussetzung. Eine native Windows-EXE wurde nicht erzeugt. Nach Freigabe der GitHub-Abrechnung können die Workflows erneut gestartet werden.

## Offene Live-Prüfungen

- Authentifizierte echte Modellaufträge mit allen verwendeten Provider-/Modellkombinationen.
- Begleitung eines tatsächlichen Limit-/Reset-Zyklus; Zeitfenster und Wiederaufnahme sind bisher deterministisch getestet.
- Interaktive Desktop-Prüfung auf einem eigenen Windows-Rechner, zusätzlich zu einem möglichen CI-Runner-Test.
- Langzeitbetrieb und harte Prozess-Kills mit möglicherweise überlebenden nativen Kindprozessen.
- Messung der Routingheuristik gegen reale Verbrauchsverläufe; es wird kein nachgewiesenes globales Optimum der Abo-Ausschöpfung behauptet.


## Agent Fleet 0.3 · THE-FIN-Desktop

93 Tests mit Tk bestanden. Native macOS-App und portable `.pyzw` starten mit eingebetteter Albert Sans; beide haben drei verbundene Accounts ohne Abfragefehler gelesen. Die native App wurde bei 1280 × 840 geprüft, der visuelle Vergleich bei 1568 × 956 sowie 760 × 700. [Design-Abnahme](../design-qa.md) und [maschinenlesbarer Nachweis](desktop-redesign-validation.json). Windows-EXE und Windows-GUI bleiben unbestätigt; die bestehende GitHub-Abrechnungsblockade gilt weiter.
