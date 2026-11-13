# CLI und Betrieb

[Zurück zur Übersicht](../README.md) · [Installation](quickstart.md)

## Quoten und Warten

- **Codex:** Metadatenabfrage über den dokumentierten `account/rateLimits/read`-Aufruf des nativen `codex app-server`. Der Worker aktualisiert bei anstehenden Jobs höchstens einmal pro Minute pro Profil. Kein Modellaufruf für die Quotenabfrage. Alle Slots werden anhand ihrer gemeldeten Dauer ausgewertet, nicht pauschal als fünf Stunden und Woche interpretiert.
- **Claude:** Gemeldete `rate_limit_event`-Informationen aus dem nativen CLI-Stream werden gespeichert. Vor dem ersten Auftrag und bei CLI-Versionen ohne solche Events können Quoten unbekannt sein. Der Broker liest keine privaten Claude-Usage-HTTP-Endpunkte. Eine im nativen `/usage` beobachtete Quote lässt sich manuell erfassen.
- Ein Account ist erst wieder verfügbar, wenn **alle anwendbaren ausgeschöpften Fenster** zurückgesetzt sind. Bei gleichzeitig leerem Fünf-Stunden- und Wochenfenster gilt der spätere Reset. Neue Aufträge bevorzugen unter verfügbaren Profilen das Wochenkontingent mit dem frühesten gemeldeten Reset; Gleichstände werden nach letzter Nutzung aufgelöst.
- Eine unbekannte Quote erlaubt einen ersten nativen Versuch. Meldet dieser ein Limit ohne Reset-Metadaten, wird das Profil angehalten. Der Broker erfindet weder einen Reset in fünf Stunden noch eine verbleibende Tokenzahl. Eine spätere erfolgreiche Codex-Quotenabfrage oder eine manuelle Beobachtung kann die unbekannte Sperre klären.
- Der Prozess `work` muss für automatische Wiederaufnahme laufen. Bei Mac-Ruhezustand läuft kein Auftrag weiter; nach dem Aufwachen prüft der Worker erneut. Nach einem Neustart `work` erneut starten. Queue und Ergebnisse bleiben erhalten. Es wurde kein Autostart-Dienst installiert.

Beispiel für eine **tatsächlich beobachtete** Quote: Setze `FIVE_HOUR_RESET` und `WEEKLY_RESET` zuerst auf die vom Provider gemeldeten künftigen ISO-8601-Zeitpunkte.

```sh
agent-fleet quota set claude-1 --window five-hour --used 100 --reset-at "$FIVE_HOUR_RESET"
agent-fleet quota set claude-1 --window weekly --model opus --used 75 --reset-at "$WEEKLY_RESET"
```

`quota show` liefert beobachtete Fenster, Zeitpunkte und Sperrgründe; `quota_known:false` heißt unbekannt. Die Anzeige ist eine Beobachtung, keine Reservierung: Nutzung in einer anderen App kann den verbleibenden Anteil zwischen zwei Abfragen ändern. GPT- und Claude-Modelle bleiben getrennt; kein automatischer Provider- oder Modellwechsel ohne expliziten Auftrag.

## Lebenszyklus und Prozessgrenzen

`queued → running → succeeded`; bei Limits `waiting`; bei Fehlern `failed` oder `needs_review`. Ein Worker pro lokalem Queue-Verzeichnis; mehrere Agenten dürfen gleichzeitig einreichen und Ergebnisse lesen. Der erste Stand verarbeitet Jobs nacheinander. Zwei Worker in getrennten State-Verzeichnissen koordinieren sich nicht.

`--key` macht identische Einreichungen idempotent, einschließlich gleichzeitig eingehender Einreichungen. Ein anderer Auftrag mit demselben Schlüssel wird abgewiesen. Maximal sechs native Versuche pro Job, konfigurierbar mit `--max-attempts`. Warten ohne Modellstart verbraucht keinen Versuch. `--timeout` begrenzt einen nativen Versuch, Standard 1.800 Sekunden. `run --wait-seconds` begrenzt das Warten zwischen Versuchen; einen bereits laufenden nativen Versuch beendet weiterhin dessen `--timeout`.

Bei einem Limit während eines Schreibauftrags, Timeout oder Workerabbruch ist die bisherige Arbeit möglicherweise teilweise ausgeführt. Der Broker startet sie nicht automatisch neu. Nach einem harten Betriebssystemabbruch können native Kindprozesse noch laufen: zuerst Prozesse und Arbeitsverzeichnis prüfen, dann explizit freigeben:

```sh
agent-fleet work --once
agent-fleet job retry <id>
agent-fleet profile release <name>
```

`work --once` markiert beim Wiederanlauf verwaiste `running`-Einträge als `needs_review`. `job retry` ist nur für angehaltene terminale Jobs möglich; damit bestätigt der Bediener die Prüfung. `profile release` hebt nur einen lokalen Hold auf und schafft kein Provider-Kontingent. Jobabbruch: `job cancel <id>` für einen noch nicht laufenden Auftrag. Ein aktiver Worker reserviert nur die Ausführung; wartende Jobs können parallel abgebrochen und Profile für nachfolgende Starts pausiert werden. Native Login- und Jobprozesse desselben Profils sind durch einen Account-Lock serialisiert.

## Daten und Einrichtung

Standard-State ist lokal: macOS `~/Library/Application Support/AgentPool`, Windows `%LOCALAPPDATA%\AgentPool`, Linux `~/.local/share/agent-pool`. `AGENT_POOL_HOME` oder `--home` überschreibt diesen Ort. SQLite, Aufgaben, Ergebnisse und native Profilverzeichnisse gehören **nicht in OneDrive/SharePoint oder auf ein Netzlaufwerk**. Auf Windows die persönlichen Verzeichnisberechtigungen des Betriebssystems verwenden; auf POSIX werden State-Verzeichnisse mit 0700 angelegt.

Die Provider-CLIs verwalten ihre eigenen Credentials unter `CODEX_HOME` bzw. `CLAUDE_CONFIG_DIR`. Der Broker kopiert keine Tokens in seine Datenbank. Bekannte geerbte API-Keys und Provider-Endpunkt-Overrides werden aus der Kindprozessumgebung entfernt, damit ein Subscription-Auftrag nicht unbemerkt über einen geerbten API-Key läuft. Native Profilkonfiguration oder vom Nutzer aktivierte Extra-Usage kann trotzdem abrechnungsrelevant sein; der Broker ist keine Abrechnungssperre. Aufgaben und Ergebnisse sind lokal im Klartext gespeichert und können vertrauliche Inhalte enthalten. Offensichtliche Bearer-/API-Key-Muster in Ergebnissen und Providerfehlern werden redigiert; das ist kein umfassender Secret-Scanner.

Nutzung bleibt an die Bedingungen des jeweiligen Accounts gebunden. Mehrere Profile vereinigen keine Token-Guthaben und erlauben keine Umgehung von Anbieterbeschränkungen. Diese Version ist für eigene autorisierte lokale Profile gedacht. Ob ein bestimmtes Multi-Account-Setup nach den Vertragsbedingungen zulässig ist, wird durch dieses Programm nicht entschieden.

## Prüfen

```sh
python3 -m unittest discover -s tests -v
python3 scripts/build_zipapp.py
python3 dist/agent-fleet.pyz --version
```

Die Prozess-Tests starten echte Betriebssystemprozesse mit kontrollierten Provider-Fixtures. Sie testen keine echte Modellantwort. Der Bericht [`docs/validation.md`](validation.md) trennt lokale Prüfungen, echte CLI-Protokollprüfungen und offene Live-/Windows-Prüfungen.


## Remote

Für zentrale Linux-Pools steht `--remote <Name>` vor dem Unterbefehl. Remote-Aufträge verwenden registrierte `--workspace`-Namen und verpflichtende stabile `--key`-Werte; der Client liest `--prompt-file` lokal. Remote-`run` übermittelt und wartet, startet aber keinen Worker. Einrichtung, eingeschränkte SSH-Schlüssel und Dienste: [Remote-Anleitung](remote.md).
