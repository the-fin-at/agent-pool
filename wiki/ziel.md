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

## Nutzerkorrektur vom 2026-10-28: Ausführungsziel pro Projekt

Johannes legte später ausdrücklich fest, dass das Ausführungsziel projektabhängig ist und er es dem Chief of Staff mitteilt. Die genaue Korrektur und Quelle stehen in [Entscheidungen](entscheidungen.md). Ein maschinenweites Ausführungsstandardziel, insbesondere `claw-remote`, wird dadurch nicht aus der persönlichen Präferenz abgeleitet. Vor einem neuen Fleet-Auftrag muss das Ziel für das jeweilige Projekt aus dem autorisierten Projektauftrag bekannt sein; fehlt es, wird kein neues Ziel geraten und kein Auftrag eingereicht.

Native Accounts, SSH-Verbindungen und lokale Hostkonfiguration bleiben maschinenlokal. Der Projektauftrag benennt dagegen das gewählte Ausführungsziel und gegebenenfalls den registrierten Workspace. Die Korrektur ändert die laufende Integration nicht in eine neue Remote-Beauftragung.

## Umgesetzter Zielvertrag: Checkpoint vom 2026-10-28

Die zuvor geforderte ausdrückliche Projektzuordnung wurde mit [PR #18](https://github.com/the-fin-at/agent-pool/pull/18), `the-fin-at/agent-pool@2d7774cad132a542cdf99c8eaf7b3b4567794d90`, als Skill-/Übergabevertrag geliefert. Die [Projektziel-Anleitung](../skills/agent-fleet/references/project-target.md) legt Identität, lokale Arbeitskopie bzw. Remote-Verbindung und Serverworkspace/-pfad fest. Sie gewährt keine zusätzliche Bearbeitungs-, Merge-, Deployment- oder Nachrichtenbefugnis. Es wurde kein neues Runtime-Konfigurationsschema eingeführt. Die gemeinsame Rust-Abnahme bleibt ein eigener, noch zu belegender Schritt.

## Gemeinsames Integrationsergebnis vom 2026-10-28

Der unmittelbar beauftragte Integrationsumfang wurde mit [PR #22](https://github.com/the-fin-at/agent-pool/pull/22) auf `the-fin-at/agent-pool@9f018a1ff90f9da0b8fba1a90e3ee02c67e142f7` zusammengeführt. Der endgültige geprüfte Code `c47144087d3d7f665600ef0183af1c94dcd5180d` enthält die Claude-, Profilwahl-, Projektziel- und Busy-Fortschrittsverträge samt beider späterer Reviewkorrekturen. Die [Abnahmequellen](../docs/rust-migration.md) und [Reviewbelege](../docs/reviews/rust-tauri-review.md) grenzen tatsächliche Mac-/Linux-Prüfungen, kontrollierte Provider und Paketmetadaten voneinander ab.

Mac-CLI und App wurden als 0.5.0 mit den gemergten Releasehashes geprüft. Der produktive Linux-Worker blieb auf Python 0.4.2; Rust 0.5 wurde dort isoliert getestet. Die Planung bis 1.0 bleibt ein eigener, priorisierter Arbeitsauftrag im [Releaseplan](release-1.0.md). Der Abschluss dieser Integration behauptet weder einen vollständig abgenommenen Windows-Support noch eine grüne GitHub-CI oder einen öffentlichen notarisierten Release.

## Erweiterter Auftrag und Produktionscheckpoint vom 2026-10-29

Johannes beauftragte im Chief-of-Staff-Chat `01a18453-50f4-7463-a3a6-9a45c56297d7` ausdrücklich, den bestehenden produktiven Linux-Pool auf Rust 0.5 umzustellen, Accounts/Jobs zu bewahren und danach die übrigen 1.0-Gates weiterzubearbeiten. Dieser spätere Auftrag ergänzt den am 28.10. abgeschlossenen Integrationsumfang. Der [Produktionsnachweis](../docs/production-upgrade-2026-10-29-validation.json) und unabhängige Postcheck bestätigen die Umsetzung mit erhaltenen sieben vollständigen alten Jobs, sechs Profilen/vier aktivierten Accounts sowie unveränderten Auth-Verzeichnissen und Workspaces.

Die anschließenden zwei echten read-only Providerjobs liefen erfolgreich über den nativen Produktionsworker; der damalige Gesamtbestand wuchs dadurch auf neun erfolgreiche Jobs. Ein vollständiger befüllter Upgrade-/Rollback-Fehlerkatalog und Performancegates waren damit noch nicht abgenommen, sondern bereits getrennt in Bearbeitung. Mangels Windows-Maschine wählte Johannes ausdrücklich die Fortsetzung der übrigen Gates; die native Windows-Abnahme bleibt offen und Teil der 1.0-Planung. Quelle und Grenzen: [Betriebsrunbook](../docs/production-upgrade-2026-10-29.md), [Aufträge](auftraege.md), [Releaseplan](release-1.0.md).
