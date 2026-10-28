# Agent Fleet 0.4 – Übersicht und Anmeldung

final result: passed

## Bezug und tatsächliche Prüfung

Bezug ist der vom Nutzer bereitgestellte ChatGPT-/Codex-Kontextwechsler. Er wird als Lokal-/Remote-Wechsel in die bestehende helle THE-FIN-Oberfläche übertragen. Ziel ist eine Account- und Kontingentübersicht; Auftragsmanagement bleibt beim CLI-/Skill-Betrieb. Quelle und finale native Fensteraufnahme wurden zusammen im selben Vergleich betrachtet. Es wird keine Kopie der dunklen Referenzfarben behauptet.

Die Aufnahmen stammen aus einem tatsächlichen Tk-Fenster, Albert Sans aus den eingebetteten Assets. Die normalen Aufnahmen haben 1280 × 900 Inhaltsgeometrie, die schmale Ansicht 760 × 840. Screenshots enthalten ausschließlich Beispieldaten. CUA war wegen der bestehenden Symlink-Umgebung nicht ausführbar; die Fensteraufnahmen wurden per macOS-Screenshot-Werkzeug erzeugt und visuell geprüft.

## Nachweise

- [Referenz](design/2026-10-28/overview/reference-context-switch.png)
- [Lokal](design/2026-10-28/overview/local.png)
- [Geöffneter Kontextwechsler](design/2026-10-28/overview/context-switch.png)
- [Remote-Verbindungen](design/2026-10-28/overview/remote-connections.png)
- [Verbindung im Hauptfenster](design/2026-10-28/overview/connection-form.png)
- [Integrierter Geräte-Login](design/2026-10-28/overview/device-login.png)
- [Schmale Ansicht](design/2026-10-28/overview/narrow-local.png)

## Vergleich und Korrekturen

1. Kontextwechsel oben statt technischer Server-Comboboxen. Zwei klar beschriftete Auswahlflächen mit sekundärer Beschreibung, eigener Auswahlmarkierung und Escape-/Außenklick-Verhalten.
2. Lokale Accounts und entfernte Verbindungen sind getrennte Ansichten. Nach Öffnen eines Servers erscheint dessen Account-Übersicht. Die Remote-Statuszeilen übernehmen keinen lokalen Datenstand.
3. Auftragskomponist und System-Pop-ups sind aus dem Dashboard entfernt. Verbindung, Login und Details liegen im Hauptfenster.
4. Die erste Aufnahme zeigte abgeschnittene Formulare durch verbliebene gleichmäßige Account-Grid-Gruppen. Die Gruppen werden beim Seitenwechsel zurückgesetzt; die tatsächliche Formularbreite ist regressionsgetestet. Finale Aufnahmen zeigen alle Felder und Aktionen vollständig.
5. Überbreite Icon-Schaltflächen und die doppelte ausgewählte Menüfläche wurden reduziert. Körpertext und Metadaten bleiben aufrecht; die Brand-Rollen stammen aus THE-FIN.
6. 760 px: die Seitenleiste wechselt zu kompakter Anbieter-Navigation; Kontextschalter, Suche, Hinzufügen und Kreis-/Wochenanzeige bleiben erreichbar. Weitere Accounts werden regulär vertikal gescrollt.

Keine offenen P0/P1/P2-Befunde im geprüften Ablauf. Native Checkboxen, Radioelemente und Scrollleisten bleiben plattformspezifisch (P3); dies ist keine Behauptung einer Windows- oder vollständigen Accessibility-Abnahme.

## Funktions- und Laufzeitnachweise

118 Tests mit echtem Tk bestehen. Die native UI führt einen kontrollierten Geräte-Login bis zum verbundenen Account aus. Die echte UI → OpenSSH → Linux → Provider-Test-CLI → UI-Kette besteht einschließlich Claude-Rückgabecode, Gerätecode, eingeschränktem SSH-Schlüssel und unabhängiger serverseitiger Prozesse. Details: [SSH-Nachweis](docs/remote-ssh-validation.json).

Das tatsächlich gebaute Mac-App-Paket startet den Login-Hintergrundprozess und bestätigt den kontrollierten Account. Drei vorhandene reale Accounts werden per nativer Metadatenabfrage ohne Fehler angezeigt; Albert Sans ist geladen. [Paket-Nachweis](docs/overview-packaged-login.json), [App-Nachweis](docs/overview-native-smoke.json).

Die echten Provider-CLIs wurden mit leeren isolierten Profilen auf den Flow-Start geprüft; Claude verarbeitet die Pipe-Eingabe und lehnt einen ungültigen Code erwartungsgemäß ab. Eine neue reale Browser-Zustimmung des Accountinhabers auf einem produktiven Linux-Host ist damit nicht ersetzt. Native Windows-UI und neue Windows-EXE bleiben ungeprüft.
