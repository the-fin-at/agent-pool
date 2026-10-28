# Agent Fleet 0.4 · Übersicht und Login

Das Dashboard zeigt verfügbare Accounts und ihre Kontingente. Die Agenten vergeben und bearbeiten Aufträge über CLI und Skill. Der Desktop dient der Übersicht, der Verbindung von Rechnern und der Anmeldung von Accounts.

## Lokal und Remote

Oben links wechselt der Kontextschalter zwischen **Lokal** und **Remote**, mit demselben Prinzip wie der ChatGPT-/Codex-Wechsel im bereitgestellten Screenshot.

- **Lokal** zeigt die Accounts dieses Rechners. Der bestehende native Codex-Hauptaccount bleibt eine zusätzliche Anzeigequelle.
- **Remote** zeigt zuerst die eingerichteten Verbindungen. „Öffnen“ führt zu den Accounts dieses Servers. Lokale Accounts werden dort nicht beigemischt.
- Anbieterfilter, Suche, Kontingentkreise und Wochenbalken gelten für den gewählten Rechner. Veraltete und unbekannte Werte bleiben als solche erkennbar.

Account-Details, neue Verbindungen und Login befinden sich innerhalb des Hauptfensters. Die alten Auftragsfenster und technischen Server-Comboboxen sind aus dem Dashboard entfernt. Der CLI-/Skill-Auftragsbetrieb bleibt verfügbar.

## Verbindung hinzufügen

Unter Remote auf **Verbindung hinzufügen** klicken. Namen und SSH-Adresse bzw. SSH-Alias eingeben. Agent Fleet erkennt seine Installation und den State-Pfad auf dem Server automatisch und prüft die Verbindung vor dem Speichern.

Voraussetzungen auf Linux: Python 3.11+, Agent Fleet 0.4, native Provider-CLI, bereits eingerichteter SSH-Schlüsselzugang und ein geprüfter Host-Key. Die einmalige [Servereinrichtung](remote.md) bleibt erforderlich. Das Dashboard verwaltet keine SSH-Passwörter und akzeptiert Host-Keys nicht ungeprüft.

Für eigene State-Pfade oder eingeschränkte Forced-Command-Schlüssel die erweiterten Einstellungen öffnen und Executable sowie Datenverzeichnis ausdrücklich eintragen. Auch dieser Weg prüft, ob der Server die Login-Funktion unterstützt. Lesbare Verbindungsnamen dürfen Leerzeichen enthalten. „Entfernen“ löscht nur die lokale Verbindungszuordnung, keine Serverdaten oder Accounts.

## Account direkt in der App anmelden

1. Lokal oder einen konkreten Remote-Server öffnen.
2. **Account hinzufügen** anklicken und Codex oder Claude auswählen.
3. Einen Namen wie Privat oder Arbeit eingeben und die Anmeldung starten.
4. Die offizielle Anbieter-Anmeldung im Browser bestätigen.

**Codex:** Die native CLI liefert den Gerätecode. „Code kopieren“ übernimmt ihn; „Im Browser anmelden“ öffnet die offizielle Device-Seite. Device-Anmeldung muss gegebenenfalls in den ChatGPT-/Workspace-Einstellungen erlaubt werden. Neue Codex-Profile ohne vorhandene Konfiguration erhalten dateibasierte Credential-Speicherung, damit ein Headless-Dienst keinen entsperrten Desktop-Keyring voraussetzt. Eine bestehende Konfiguration wird dabei erhalten.

**Claude:** Den offiziellen Browser-Link öffnen. Wenn der Browser einen Code statt eines lokalen Callbacks zeigt, den vollständigen Code in der integrierten, maskierten Eingabe einfügen und **Anmeldung abschließen** anklicken. Das ist insbesondere beim Remote-Server normal.

Nach bestätigtem nativen Login prüft Agent Fleet die native CLI-Anmeldung und aktualisiert die Account-Übersicht. Es werden keine Tokens aus Credential-Dateien ausgelesen oder zwischen Rechnern kopiert. Der Anmeldevorgang findet auf dem ausgewählten Rechner statt; der Browser darf auf dem Client laufen.

Die Bestätigung beim Anbieter bleibt eine menschliche Aktion. Die App fragt kein ChatGPT-/Claude-Passwort ab. Bei ungültigem, abgelaufenem oder unvollständigem Code erscheint ein Fehler mit einem neuen Versuch.

## Abbruch und Wiederholung

Beim Verlassen der Login-Ansicht, Wechsel des Rechners oder Schließen des Fensters wird die laufende Anmeldung abgebrochen. Ein beim Schließen gestarteter Hilfsprozess sendet den Abbruch unabhängig vom GUI-Fenster. Ist der Server nicht erreichbar, bleibt die Session zeitlich auf 15 Minuten begrenzt. Ein bereits vom Anbieter bestätigter Abschluss wird als solcher verarbeitet; Abbrechen ist kein Logout.

Ein stabiler Anmeldeschlüssel verhindert doppelte Starts nach einer verlorenen SSH-Antwort. Genau ein Poll pro Ansicht liest den Status. Wiederholte Statusantworten bauen das Code-Eingabefeld nicht neu auf. Späte Antworten eines vorherigen Rechners oder einer alten Anmeldung überschreiben die aktuelle Ansicht nicht.

Native Accountprozesse sind gegeneinander gesperrt. Ein aktiver Login deaktiviert einen bestehenden Account nicht dauerhaft. Ein belegter Account meldet einen klaren Fehler. Auf Linux wird, wenn verfügbar, ein kurzlebiger systemd-User-Dienst verwendet; sonst ein entkoppelter Hintergrundprozess. Die reguläre Server-Worker-Einrichtung mit Linger ist für dauerhaften Betrieb weiterhin empfohlen.

## Technische Schnittstelle für Agenten

Die Anmeldung ist auch über die CLI verfügbar. Codes möglichst per Datei oder stdin übertragen:

```sh
agent-fleet --remote zentral auth start privat --provider codex --key 0123456789abcdef0123456789abcdef
agent-fleet --remote zentral auth get SESSION_ID
agent-fleet --remote zentral auth input SESSION_ID --code-file -
agent-fleet --remote zentral auth cancel SESSION_ID
```

Pro Versuch einen neuen zufälligen UUID-Hex-Schlüssel verwenden; das Beispiel ist nur ein Formatbeispiel. Die SSH-Kommandozeile enthält keine Login-Codes. RPC liest keine vom Client angegebenen Dateien auf dem Server. Native Anmeldedaten verbleiben im privaten Profilverzeichnis des Zielrechners.

## Nachweise und Grenzen

- Echte native Codex- und Claude-CLI: Start der Browser-/Device-Flows mit leeren isolierten Profilen geprüft. Claude verarbeitet einen eingegebenen Testcode ohne TTY und lehnt einen absichtlich ungültigen Code kontrolliert ab. Bestehende Logins wurden dafür nicht verändert.
- Echte Tk-UI mit kontrollierter nativer CLI: vom Anmeldebutton bis zum verbundenen Account und seiner Identität geprüft.
- Echte Mac-UI → OpenSSH → Linux-Container → native Provider-Test-CLI → zurück zur Account-Übersicht: Gerätecode und Claude-Code inklusive eingeschränktem SSH-Schlüssel geprüft. Siehe [maschinenlesbarer Nachweis](remote-ssh-validation.json). Die Provider-Test-CLI kontaktiert keinen Anbieter und verwendet keine echten Zugangsdaten.
- Fensteraufnahmen und schmale Ansicht: [Design-Abnahme](../design-qa.md). Screenshots enthalten ausschließlich Beispieldaten.
- Ein vollständiger neuer Provider-Login mit menschlicher Browser-Zustimmung auf einem konkreten produktiven Linux-Host sowie native Windows-UI-Abnahme stehen weiterhin aus. Es wurde kein persönlicher Server bereitgestellt. GitHub-CI ist separat zu betrachten.


Vor dem Merge des 0.4-Pull-Requests den Branch `feat/overview-connections-login` aus `the-fin-at/agent-pool` für Client und Server verwenden. Ältere Release-Pakete unterstützen die neue Anmeldung noch nicht.
