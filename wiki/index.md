# Agent Fleet: Koordinationswiki

Ersteintrag: 2026-10-28. Dieses Wiki bewahrt datierte Entscheidungen und Belege. Es ersetzt weder den ausführenden Code noch eine erneute Statusprüfung. Änderungen werden als neue datierte Einträge ergänzt; überholte Aussagen behalten ihren Beleg und erhalten einen Verweis auf den Nachfolger.

## Ziel und Produktentscheidungen

- [Zielauftrag](ziel.md): Auftrag, Grenzen und ambitionierter Maßstab für Version 1.0.
- [Entscheidungen und Ausgangsbasis](entscheidungen.md): Produktvertrag, belegte 0.4.2-Basis und offene Abgrenzungen.

## Durchführung und Abnahme

- [Aufträge und Integration](auftraege.md): Zuständigkeiten der laufenden Chats, Abhängigkeiten und Übergaberegeln.
- [Releaseplan 1.0](release-1.0.md): Etappen, Prüfmatrix, messbare Gates und fehlende Nachweise.

## Quellenführung

Am 2026-10-28 wurde der Wiki-Ort `agent-pool/wiki/` von Johannes im Chief-of-Staff-Chat `01a18453-50f4-7463-a3a6-9a45c56297d7` bestätigt. Quellen werden verlinkt, nicht als Transkripte kopiert. Repo-bezogene Ausgangsaussagen beziehen sich auf `the-fin-at/agent-pool@50e42972e599c76db324ccaa7a7643a3e7de9c72`, sofern ein Eintrag keinen anderen Stand nennt.

## Verifizierter Integrationscheckpoint vom 2026-10-28

[PR #15](https://github.com/the-fin-at/agent-pool/pull/15) schloss den Profilwahl-/Skill-Strang ab; die anschließend lokal geprüfte gemeinsame `main`/`origin/main`-Basis war `3c9d7faf53025a1271f6ad65e2ea4a0c25e9e548`. Abschlussbelege und der daraus folgende nächste Integrationsschritt ergänzen [Aufträge](auftraege.md), [Entscheidungen](entscheidungen.md) und [Releaseplan](release-1.0.md). Frühere offene Beobachtungen bleiben als Verlauf erhalten.

## Nutzerkorrektur und Abnahmecheckpoint vom 2026-10-28

Die [Zielauswahl pro Projekt](entscheidungen.md) ersetzt die frühere persönliche maschinenweite Standardziel-Empfehlung. [Zielauftrag](ziel.md), [Auftragsübersicht](auftraege.md) und [Releaseplan](release-1.0.md) enthalten den daraus folgenden Vertrag. Zusätzlich dokumentiert die Auftragsübersicht den Merge dieses Wikis über PR #16 und einen getrennten kontrollierten Python-Prozessnachweis; daraus folgt keine Rust-Abnahme.

## Abschluss des Projektziel-Strangs am 2026-10-28

[PR #18](https://github.com/the-fin-at/agent-pool/pull/18) brachte die projektbezogene Zielwahl auf `main` bei `2d7774cad132a542cdf99c8eaf7b3b4567794d90`. [Entscheidungen](entscheidungen.md), [Aufträge](auftraege.md) und [Releaseplan](release-1.0.md) ergänzen Vertrag, abgegrenzte Nachweise und den nächsten Rust-Schritt. Der gemeinsame Checkout wurde anschließend kontrolliert auf diesen Stand gebracht; die zuvor untracked Wiki-Kopie blieb byte-identisch gesichert.

## Integrationsbefund vom 2026-10-28: belegter Account blockiert andere Arbeit

Ein unabhängiges Review identifizierte einen gemeinsamen Python-/Rust-Schedulingfall: ein belegter nativer Accountlock kann die Bearbeitung weiterer verfügbarer Profile oder Jobs anhalten. [Entscheidungen](entscheidungen.md), [Aufträge](auftraege.md) und [Releaseplan](release-1.0.md) ergänzen den konkreten Fall und die getrennten Fix-Zuständigkeiten. Die Korrektur war beim Eintrag noch nicht abgeschlossen; die bisherigen Rust-Build-/Frontendberichte sind keine finale native Abnahme.

## Python-Lock-Fix abgeschlossen: Checkpoint vom 2026-10-28

[PR #21](https://github.com/the-fin-at/agent-pool/pull/21) liefert den Python-Referenzfix gegen den belegten Accountlock-Fall auf `ddbc859cbecb7c7af80fc2be918574d34d0099d7`. [Entscheidungen](entscheidungen.md), [Aufträge](auftraege.md) und [Releaseplan](release-1.0.md) trennen die gemergten 145-Test-/Lock-Belege vom noch ausstehenden finalen Rust-Kandidaten. Die produktive Serverruntime wurde dadurch nicht aktualisiert.

## Wiederaufnahme-Checkpoint vom 2026-10-28: native Abnahme weiterhin offen

Der zusätzliche Python-Gegencheck am gemergten `ddbc859` bestand. Die [Auftragsübersicht](auftraege.md) hält außerdem begrenzte Rust-Busy-Quell-/Testbelege fest. Eine später wiederholte native Mac-WebView-Prüfung lief jedoch in ein Timeout; Build und frühere Teilprüfungen sind dadurch keine finale Abnahme. [Entscheidungen](entscheidungen.md) und [Releaseplan](release-1.0.md) dokumentieren die lokale Diagnose sowie die offene direkte Nutzerzustimmung für einen zuvor automatisch abgelehnten isolierten Linux-Quelltransfer. Eine Veröffentlichung oder Produktionsaktualisierung wurde nicht daraus abgeleitet.

## Linux-Nachweis und begrenzte native UI-Auflösung: Checkpoint vom 2026-10-28

Direkte Nutzerzustimmung ermöglichte die isolierten Linux-Tests; 22 native Fälle und 100 eindeutige kontrollierte Ausführungen bestanden auf dem echten Host. Die [Auftragsübersicht](auftraege.md) und [Entscheidungen](entscheidungen.md) grenzen diese Belege sowie einen historisch bestätigten 23-Schritt-Mac-Nachweis vom weiterhin nicht akzeptierten finalen Kandidaten ab. Zwei spätere Reviewfälle benötigen Korrektur, betroffene Wiederholungsprüfungen und erneutes Review; siehe [Releaseplan](release-1.0.md).

## Abgeschlossene 0.5-Integration vom 2026-10-28, 23:18 Uhr Wien

[PR #22](https://github.com/the-fin-at/agent-pool/pull/22) ist gemergt; `main` wurde bei `9f018a1ff90f9da0b8fba1a90e3ee02c67e142f7` geprüft. Rust/Tauri, Claude-Fensterkorrektur, automatische Profilwahl, projektbezogene Zielwahl und native Lock-Fortschritte sind auf gemeinsamer Basis zusammengeführt. Der endgültige Code-/Reviewstand ist `c47144087d3d7f665600ef0183af1c94dcd5180d`; der PR-Head `a277c5525b9371017e65ca1b43c1fcd863424996` ergänzt anschließend nur Belege und die native Fensteraufnahme.

[Zielauftrag](ziel.md), [Entscheidungen](entscheidungen.md) und [Auftragsübersicht](auftraege.md) führen Abschluss, tatsächliche Nachweise und Installationsgrenzen. Der [Releaseplan](release-1.0.md) priorisiert die noch offenen 1.0-Gates. Version 0.5 ist kein behaupteter 1.0-Release: Windows, gehostete CI, gezielte Performance-/Upgrade-/Rollback- und Vertriebsnachweise bleiben gesondert zu liefern. Frühere offene Integrationsmeldungen sind durch diesen datierten Abschluss überholt, bleiben aber als Verlauf erhalten.
