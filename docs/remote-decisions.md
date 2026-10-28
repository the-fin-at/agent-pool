# Remote-Erweiterung: Ziel und Entscheidungen

Ziel über die Verbindung hinaus: Ein persönlicher Agent Fleet arbeitet auf Linux weiter, während Mac- und Windows-Clients nur verwalten. Umgesetzt wird die zweite Stufe: verschlüsselte Verbindung plus dauerhafte serverseitige Queue/Worker. Der Nachweis ist ein unterbrochener SSH-Client mit anschließend genau einer Ausführung im Linux-Testcontainer.

`be-ambitious`: Altitude erhöht den Anspruch von „remote prompten“ zu einem zuverlässigen Ablauf mit Rückmeldung. Depth startet bei SQLite-Zuständen, OS-Locks und nativen Prozessen. Harte Kriterien: keine automatische Doppelausführung bei verlorener Antwort, kein Modelljob im RPC-Prozess, keine Prompt-Interpolation in Shell-Kommandos und weiterhin funktionsfähiger lokaler Broker. Range wurde zugunsten gezielter Codeprüfung durch das ausdrücklich gewünschte Opus 5.5 ausgelassen.

## Opus 5.5

Die native Claude-CLI wurde mit dem exakten Modell `claude-opus-5-5`, ohne Tools und ohne Fallback aufgerufen. Die Antwortmetadaten bestätigten `canonicalModel: claude-opus-5-5` und `is_error: false`. Zuerst Architekturberatung anhand des bestehenden Codes, danach Prüfung der konkreten Implementierung. Das Gutachten ist eine unabhängige Fehlersuche; die ausführbaren Tests entscheiden über die Funktionsnachweise.

Übernommene Kernbefunde:

- Globaler Worker-Lock reserviert nur noch den Executor. Cancel/Retry verwenden bedingte SQL-Updates; ein zwischen Auswahl und Start abgebrochener Job kann nicht mehr gestartet werden.
- Native Jobs, Login und Codex-Metadaten derselben verwalteten Identität verwenden einen Account-Lock. Ein belegter Account wartet ohne verbrauchten Ausführungsversuch.
- RPC führt keine Jobs aus und kann keine Client-Pfade bzw. fremden State-Verzeichnisse als Task-Parameter übernehmen. Remote-`run` ist submit + wait.
- SIGTERM führt über den bestehenden Cleanup-Pfad. systemd verwendet `KillMode=control-group`; Heartbeat bleibt auch während langer nativer Jobs aktiv.
- Headless Device-Login, feste Server-Pfade, strikte Host-Key-Prüfung, kein Agent-Forwarding, explizites UTF-8, Größenlimits und verpflichtende Remote-Schlüssel.

## Bewusste Grenzen

Der Dienst ist ein persönlicher Pool innerhalb eines Unix-Accounts. Vollständige Isolation zwischen unterschiedlichen Personen, Container-Sandboxen pro Job, Account-Deduplizierung, parallele Executor, Ergebnis-Streaming und automatische Dateisynchronisierung bleiben außerhalb dieser Erweiterung. Benannte Workspaces verhindern versehentliche Pfadverwechslungen; sie sind keine allgemeine Dateisystem-Sandbox.

Der dauerhafte Worker aktualisiert verwaltete Account-Metadaten im Leerlauf etwa alle 60 Sekunden. RPC und Remote-Desktops lesen ausschließlich den Cache. Lokale Monitor-Abfragen bleiben per Profil-Lock mit verwalteten nativen Jobs serialisiert. Der native Hauptaccount außerhalb verwalteter Profile kann weiterhin auch von externer Codex-Software verwendet werden; deren Prozesse nehmen nicht an Agent-Pools Lock-Protokoll teil.

Remote-Metadaten werden im Desktop sitzungsbezogen gehalten. Entwürfe und Auftragsschlüssel muss der Benutzer bei einem App-Neustart selbst wiederverwenden; die CLI verlangt stabile Schlüssel. SSH-Shell-Zugang bleibt für Einrichtung und Inspektion erhalten. Optional eingeschränkte Forced-Command-Schlüssel steuern ausschließlich den RPC-Endpunkt.


## Behobene Befunde der zweiten Opus-Prüfung

Account-busy liefert einen Leerlauf-Tick und löst dadurch die normale Poll-Pause aus. Remote-Monitoring ist cache-only; die laufende Worker-Schleife aktualisiert die Metadaten. Lokale Managerfenster serialisieren RPC-Ausgaben über einen gemeinsamen Lock. Der Manager erzeugt nach bestätigtem Submit einen neuen Schlüssel und behält ihn bei Fehlern. Fehlende Remote-Konfiguration lässt den Refresh-Button bedienbar. RPC-Argumenthilfe wird aufgefangen; ungültige Executables und tiefe JSON-Verschachtelung liefern strukturierte Fehler. Der Server-State-Pfad ist in allen Client-Konfigurationen Pflicht.
