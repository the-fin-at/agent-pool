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

## Produktionswechsel und echte Provider-Abnahme vom 2026-10-29

Johannes beauftragte den produktiven Linux-Wechsel auf 0.5 mit erhaltenen Accounts/Jobs und die Fortsetzung der 1.0-Gates. Der Wechsel bestand einen unabhängigen Postcheck; danach liefen zwei echte begrenzte read-only Providerjobs über den Produktions-Rustworker. Die früheren Aussagen über den noch laufenden Python-0.4.2-Produktionsworker sind damit für diesen späteren Zeitpunkt überholt. Zum Abschluss der beiden Smokes bestanden neun erfolgreiche Jobs: sieben unveränderte alte und zwei neue.

[Produktionsrunbook](../docs/production-upgrade-2026-10-29.md), [normalisierter Upgrade-Nachweis](../docs/production-upgrade-2026-10-29-validation.json) und [echte Provider-Nachweise](../docs/native-provider-smokes-validation.json) halten die Fakten ohne rohe Prompts/Ergebnisse oder Credential-Daten fest. [Aufträge](auftraege.md) und [Releaseplan](release-1.0.md) führen die laufenden isolierten Rollback-/Performancegates; Windows, CI und Vertrieb bleiben offen.

## Weitere 1.0-Abnahme und bewusste CI-Abschaltung: 2026-10-29

Die nachfolgenden datierten Einträge in [Releaseplan](release-1.0.md), [Aufträgen](auftraege.md), [Entscheidungen](entscheidungen.md) und [Zielauftrag](ziel.md) ersetzen die zuvor offenen Upgrade-/Rollback- und Paketierungsbeobachtungen für ihre ausdrücklich geprüften Grenzen. [PR #26](https://github.com/the-fin-at/agent-pool/pull/26), [PR #30](https://github.com/the-fin-at/agent-pool/pull/30) und [PR #32](https://github.com/the-fin-at/agent-pool/pull/32) sind auf `the-fin-at/agent-pool@9a3bda9d55a92e8f5c7904d71ed6dcd3be0afce5` zusammengeführt. Die produktiven Programme blieben dieselben geprüften 0.5-Binärdateien.

Johannes ließ alle drei GitHub-CI-Workflows ausdrücklich deaktivieren. Die frühere Forderung nach Wiederherstellung gehosteter CI ist dadurch überholt; manuelle/native Nachweise bleiben erforderlich. Ein privater unveröffentlichter 0.5-Releaseentwurf enthält sechs bytegeprüfte Paketassets. [Normalisierte Betriebs-/Draftbelege](../docs/release-operations-2026-10-29-validation.json) und [Paketierungsnachweise](../docs/native-distribution.md) grenzen dies von Veröffentlichung und vollständiger 1.0-Abnahme ab. Native Windows-Abnahme, native Mac-Performance und die abschließende Vertriebs-/Releaseentscheidung blieben offen.

## Native Performance abgenommen: späterer Checkpoint vom 2026-10-29

[PR #27](https://github.com/the-fin-at/agent-pool/pull/27) wurde nach zwei unabhängigen Reviews ohne wesentlichen Befund auf `the-fin-at/agent-pool@f6c35ddb8c07c642c5a6aa5f4561947644d00bed` zusammengeführt; der finale geprüfte Head war `9d01343c0f3074269f6c751197467888087c37ea`. Die frühere gesperrte Mac-Sitzung und das dadurch offene native Performancegate sind für den späteren tatsächlich entsperrten Lauf überholt. Die [native Performanceabnahme](../docs/native-performance.md) und [Messdaten](../docs/native-performance-validation.json) belegen SSH-Statuslatenz und WKWebView-/Rust-IPC-Reaktionsfähigkeit unter echter verzögerter SSH-Antwort; [Issue #25](https://github.com/the-fin-at/agent-pool/issues/25) wurde nach Prüfung seiner Anforderungen geschlossen.

[Releaseplan](release-1.0.md), [Aufträge](auftraege.md), [Entscheidungen](entscheidungen.md) und [Zielauftrag](ziel.md) führen Resultate und Grenzen fort. GitHub-CI bleibt bewusst deaktiviert. Windows-Abnahme sowie endgültiger 1.0-Vertriebsweg, gegebenenfalls erforderliche Signierung und finale Releaseentscheidung blieben offen; der private 0.5-Entwurf wurde dadurch nicht veröffentlicht.

## Claude-Anmeldung: Diagnose und erfolgreicher Folgelauf vom 2026-10-29

Die [datierte Incident-Notiz](claude-login-2026-10-29.md) trennt den früheren tatsächlichen Versuch mit ungeklärter Ursache, den unabhängig bestätigten offenen Retry-Lockout [Issue #35](https://github.com/the-fin-at/agent-pool/issues/35) und einen später tatsächlich erfolgreichen Browser→App-Login ohne Codeänderung. [Sanitisierte Belege](../docs/claude-login-2026-10-29-validation.json) binden die beiden isolierten roten Reproduktionen und den positiven nativen Nachcheck.
