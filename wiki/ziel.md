# Zielauftrag: Agent Fleet 1.0

[Wiki-Index](index.md) · [Entscheidungen](entscheidungen.md) · [Durchführung](auftraege.md) · [Abnahmeplan](release-1.0.md)

## Auftrag vom 2026-10-28

Johannes beauftragte im Chief-of-Staff-Chat `01a18453-50f4-7463-a3a6-9a45c56297d7`, die beiden laufenden Entwicklungsarbeiten zu koordinieren, Rust-Migration, Claude-Korrekturen und Accountwechsel sauber zusammenzuführen und zu testen sowie die Version 1.0 vorauszuplanen. Den Wiki-Ort im Repository bestätigte er anschließend ausdrücklich.

Das Ziel hinter dem Auftrag: Aufträge und native Accounts sollen über Implementierungswechsel, Quotenwechsel und Prozessunterbrechungen hinweg nachvollziehbar weitergeführt werden können. Die Versionsnummer folgt den belegten Abnahmekriterien.

Der unmittelbar beauftragte Umfang umfasst Koordination, Integration und deren Prüfungen. Der [Releaseplan](release-1.0.md) beschreibt darüber hinaus die Arbeit bis 1.0; seine offenen Etappen sind keine Behauptung bereits erbrachter Leistung. Vorhandene Freigaben gelten weiter. Bezahlte neue Infrastruktur, das Ändern von Billing, neue Provider-Verträge oder zusätzliche öffentliche Dienste folgen aus diesem Plan nicht.

## Ambitioniert planen: Entscheidung vom 2026-10-28

**Altitude:** Das Ergebnis soll verlässlicher Betrieb sein. Die Leiter lautet: (1) die drei Änderungen auf einer gemeinsamen Basis integrieren; (2) Kompatibilität und Fehlerverhalten anhand desselben Release-Kandidaten nachweisen; (3) diesen Abnahmeprozess mit reproduzierbaren Fixtures und Paketnachweisen für folgende Releases erhalten.

**Depth:** Eine professionelle Releaseprüfung würde die Grenzen zwischen altem und neuem Prozess, persistierten Daten und Remote-Transport gezielt brechen. Ihr Rohmaterial sind Datenbankschemata und Zustandsübergänge, sanitisiert gespeicherte native CLI-Ereignisse, echte Betriebssystemprozesse und Paketdateien, nicht nur erfolgreiche Workerberichte. Die Methoden sind Cross-Language-Vertragstests, Fehler-/Restart-Injektion, Daten- und Prozessbeobachtung sowie Messung am öffentlichen CLI/RPC- und nativen UI-Rand. Der unabhängige Richter ist eine ausführbare Prüfmatrix plus Review des konkreten Kandidatencommits. Harte Ziele stehen im [Releaseplan](release-1.0.md); ein verfehltes Ziel bleibt rot.

**Range:** Für diese Integration wird keine zusätzliche Fachrichtung als eigener Arbeitsstrang eröffnet. Methoden der Zuverlässigkeitsprüfung fließen bereits in Depth ein. Zusätzliche Features oder Präsentationsartefakte würden die zentrale Abnahme nicht verbessern.

## Arbeitsauftrag für die ausführenden Agenten

```text
Führt Rust/Tauri, die Claude-Limitkorrekturen und automatische Profilwahl auf
aktueller gemeinsamer Basis zusammen. Erhaltet Accounts, Datenbank, Job-IDs,
Ergebnisse, native Login-Verzeichnisse und SSH/RPC-Kompatibilität. Der Desktop
bleibt Übersicht und Login; Aufträge laufen über CLI und Skills. Prüft die
Grenzen mit alten Daten, echten Prozessen und isolierten Fehlerfällen. Haltet
Prüfstand, Commit, Paket und offene Plattformgrenzen auseinander. Ergänzt nur
Arbeit, die dieses Ergebnis belastbarer macht. Bewertet den konkreten Kandidaten
mit der Release-Matrix und unabhängigen Reviews: bestanden heißt grüne Pflicht-
gates, kein Datenverlust, keine ungewollten Doppelaufträge und keine verdeckte
Wiederholung unklar ausgeführter Arbeit; fehlende Nachweise bleiben offen.
```

## Wiederaufnahme

Vor einer neuen Beauftragung: [Auftragsübersicht](auftraege.md) und Quellchat prüfen, dann den tatsächlichen Branch/Commit und die dortigen Prüfbelege lesen. Wiki-Status ist eine datierte Beobachtung. Ein offener Auftrag darf nach Kontextverlust nicht mit neuem Schlüssel dupliziert werden.
