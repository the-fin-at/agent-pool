# Entscheidungen und Ausgangsbasis

[Wiki-Index](index.md) · [Ziel](ziel.md) · [Aufträge](auftraege.md) · [Releaseplan](release-1.0.md)

## Produktvertrag, am 2026-10-28 zusammengetragen

Die folgenden Entscheidungen sind aus den beiden Quellchats überliefert und in den angegebenen Repo-Quellen belegt:

- Agent Fleet verwendet offizielle native Codex-/Claude-CLIs und deren bestehende Login-Verzeichnisse. Ein eigener OAuth-Tokenproxy gehört nicht zum Auftrag. Begriffe: [Glossar](../GLOSSARY.md).
- Der Desktop dient Übersicht, Verbindungsauswahl und nativen Logins. Jobvergabe erfolgt über CLI und Skills; eine neue Desktop-Auftragseingabe wäre eine Abweichung. Beleg bei `the-fin-at/agent-pool@50e4297`: [Übersicht und Login](../docs/overview-login.md).
- Provider und angeforderte Modelle bleiben erhalten. Automatische Auswahl zwischen geeigneten Profilen desselben Providers soll der Normalfall sein; ein ausdrücklich angeheftetes Profil ist ein eigener Vertrag. Wochen- und Modelllimits dürfen ein freies 5h-Fenster weiterhin sperren. Fehlende Werte bedeuten unbekannt. Beleg der bestehenden Grenzen bei `50e4297`: [CLI und Quoten](../docs/cli.md); die praktische Skill-Anpassung war beim Eintrag noch laufende Arbeit, siehe [Aufträge](auftraege.md).
- Tests mit kontrollierten Providern und Lastinjektion verwenden isolierte Pools. Echte Subscription-Inferenz und native UI-Belege werden getrennt ausgewiesen. Authentifizierungen und fremde Dienste bleiben erhalten. Beleg bei `50e4297`: [ADR-0001](../docs/adr/0001-real-host-validation.md).
- Geteilte Skill-/Wiki-Quellen dürfen portabel sein. Broker-SQLite, native Authentifizierung und lokale Zielpräferenzen gehören auf die ausführende Maschine. Ein persönliches Standardziel darf keine Voraussetzung des wiederverwendbaren Skills werden. Belege: [CLI-State](../docs/cli.md), [Remote-Betrieb](../docs/remote.md) und Koordinationsnachricht im Quellchat vom 2026-10-28.

## Belegte Basis vom 2026-10-28

Am Erfassungstag wurde `main` lokal bei `the-fin-at/agent-pool@50e42972e599c76db324ccaa7a7643a3e7de9c72` geprüft. Das ist der Merge von [PR #13](https://github.com/the-fin-at/agent-pool/pull/13), Version 0.4.2. Parallel dazu waren Skill-/Routing-Änderungen noch uncommitted; sie sind kein Bestandteil dieses Commits.

Die [Live-Account-Abnahme](../docs/live-account-validation.md) hält für diesen Entwicklungsstand fest: vier echte Profile lieferten korrekte Leseergebnisse, je ein Versuch; ein Claude-Nachtest war ebenfalls erfolgreich. Der Claude-Parser wurde für `unifiedWindows` und gemischte Reset-Aliasse korrigiert. Native Werte, Servercache und echte Tk-Widgets wurden verglichen. Die Testsuite umfasste 134 Tests auf dem Mac; im Linux-Lauf waren 30 GUI-Prüfungen übersprungen. Das Wiki hat diese Tests nicht erneut ausgeführt.

Der spätere 0.4.2-Nachweis überholt für Accountanmeldung und Testzahlen die früheren Zwischenstände in [0.4.1-Realhost-Abnahme](../docs/claw-remote-validation.md), README und Übersichtsdokumentation. Diese früheren Quellen bleiben als Verlauf erhalten. Die Realhost-Abnahme enthält weiterhin die relevante Methode und ihre Messgrenzen.

## Offene Abgrenzungen am 2026-10-28

Die Rust-Migration wurde im Quellchat als von `f712523` / Python 0.4.1 ausgehend beobachtet. Daraus folgt ein Integrationsbedarf für den späteren Claude-Fix und die laufende Profilwahl-Anpassung, keine Behauptung über ihre Vollständigkeit in Rust. Die technische Spezifikation liegt im Migrationsworktree unter `docs/specs/rust-tauri-migration.md`; Bezug: [Issue #12](https://github.com/the-fin-at/agent-pool/issues/12).

Der 0.4.2-Nachweis belegt eine verifizierte Ad-hoc-Signatur der bisherigen Mac-App. Er belegt weder ein signiertes/notarisiertes Tauri-Release noch eine erfolgreiche native Windows-Abnahme. GitHub-CI blieb laut Nachweis wegen Billing separat offen. Diese Grenzen sind [Release-Gates](release-1.0.md), keine grünen Ergebnisse.

Neue Erkenntnisse werden unter einem neuen Datum ergänzt und markieren betroffene Aussagen als überholt; eine Momentaufnahme wird nicht still zum dauerhaften Istzustand erklärt.

## Profilwahl-Vertrag abgeschlossen: Checkpoint vom 2026-10-28

Der später lokal geprüfte Stand `the-fin-at/agent-pool@3c9d7faf53025a1271f6ad65e2ea4a0c25e9e548` enthält den Merge von [PR #15](https://github.com/the-fin-at/agent-pool/pull/15), Quellstand `003ccfd` gegen `50e4297`. Damit ist die frühere Aussage über die noch laufende Skill-Anpassung für diesen Strang überholt. Der [Routing-Vertrag](../docs/agent-routing-contract.md) fixiert die tatsächliche Semantik: automatische zulässige same-provider Profilwahl, angeheftete Profile/Modelle bleiben erhalten, alle zutreffenden Fenster/Holds zählen, unbekannte Auslastung bleibt unbekannt und unklare Schreibausführungen werden nicht still wiederholt. Persönliche Ziele stehen in maschinenlokalem `skill-policy.json`, nicht in der geteilten Skillquelle.

Der Vertrag und [normalisierte Nachweis](../docs/agent-routing-validation.json) berichten 141 bestandene Mac/Tk-Tests, sieben isolierte Routingtests auf echtem Linux, zwei unabhängige Reviews ohne offene Befunde sowie einen echten ungepinnten Codex-Auftrag: automatisch `server-codex`, erfolgreich in einem Versuch. Der echte Auftrag hatte verfügbare Kapazität. Er beweist ungepinnte Auswahl; Erschöpfung/Failover wurden isoliert geprüft, nicht durch verfälschte oder absichtlich ausgeschöpfte reale Quoten. Dieser Python-/Skill-Nachweis ist kein Nachweis gleichwertigen Rust-Verhaltens.

## Nutzerkorrektur vom 2026-10-28: kein globales Ausführungsstandardziel

Johannes korrigierte im Quellchat „Entwirf einen CLI-Modellproxy (2)“, Turn `01a18461-3e22-7962-b4ac-29383ac55244`, ausdrücklich: „nein claw-remote soll nicht das standardziel sein, das soll projektabhängig sein und das gebe ich dem chief-of-staff als info“. Der Chief of Staff las diese menschliche Nachricht direkt.

Diese Entscheidung überholt die früher im Verlauf dokumentierte Idee einer persönlichen maschinenweiten Standardziel-Präferenz. Sie ist außerdem eine bewusste Änderung gegenüber dem in PR #15/`3c9d7fa` gelieferten `skill-policy.json`-Standardzielverhalten, keine Behauptung, dieser frühere Code hätte bereits den neuen Vertrag erfüllt. Das Ziel wird ausdrücklich pro Projekt festgelegt und vom Chief of Staff im Projektauftrag geführt. Ohne zugeordnetes Projektziel wird kein neuer Fleet-Job eingereicht; es gibt keinen stillen Rückfall auf `claw-remote`, einen anderen Host oder den lokalen Pool.

Auth-Verzeichnisse, SSH-Verbindungen und Hostparameter bleiben weiterhin lokal auf der jeweiligen Maschine. Ihre Speicherung impliziert keine globale Auswahl dieser Maschine als Ausführungsziel. Die Korrektur wurde dem Migrationsverantwortlichen übermittelt. Die zugehörige laufende Arbeit `fix/project-scoped-execution-target` war beim Checkpoint noch nicht als final gemergt belegt.

## Projektbezogene Zielwahl geliefert: Checkpoint vom 2026-10-28

[PR #18](https://github.com/the-fin-at/agent-pool/pull/18) schloss [Issue #17](https://github.com/the-fin-at/agent-pool/issues/17) ab. Am anschließend geprüften Stand `the-fin-at/agent-pool@2d7774cad132a542cdf99c8eaf7b3b4567794d90` enthält der [Routing-Vertrag](../docs/agent-routing-contract.md) im Abschnitt „Target and portability“ die neue Projektzuordnung; die [Projektziel-Anleitung](../skills/agent-fleet/references/project-target.md) beschreibt explizite aktuelle Vorgabe, Chief-of-Staff-Übergabe und eindeutige Fortsetzung desselben Projekts. Globale Präferenzen, ein allein eingerichteter Remote und andere Projekte bestimmen das Ziel nicht. Frühere offene Aussagen zum Fix-Strang sind damit überholt.

Der [Korrektur-Nachweis](../docs/project-target-validation.json) hält die Rücknahme der beiden persönlichen Standardziel-Dateien mit erhaltenen Sicherungen und überprüften installierten Skill-Hashes fest. Bestehende Account-/Verbindungsdaten blieben erhalten. Sieben isolierte Routingtests, ein Installationstest und Skillvalidatoren bestanden; die unabhängigen Standards-/Spec-Prüfungen meldeten keine offenen Befunde. Die Projektwechsel-Szenarien wurden unabhängig anhand der Anweisungen bewertet, nicht als bezahlte Live-Agentenläufe ausgeführt. Runtimecode, Dienste und echte Inferenz wurden durch diese Korrektur nicht geändert bzw. neu gestartet. Das belegt den gelieferten Anweisungsvertrag, kein zusätzliches Runtime-Projektschema.

## Scheduling-Befund vom 2026-10-28: belegter nativer Accountlock

Ein unabhängiges Integrationsreview fand auf der späteren gemeinsamen Python-Basis `the-fin-at/agent-pool@c5c141ef02eb0fc10c247226259877093cc5f39b` in [worker.py](../agent_pool/worker.py) den vorzeitigen Abschluss des gesamten Worker-Ticks bei einem `busy`-Ergebnis. Im noch uncommitted Rust-Migrationsstand wurde dieselbe Struktur in `crates/fleet-core/src/worker.rs` um Zeile 171 beobachtet; Audit-Dateihash `db98f31c8c5a`, beobachtete Basis `2d7774c`. Dieser Rust-Dateistand ist ein vergänglicher Review-Snapshot, kein finaler Kandidatencommit. Quelle: unabhängiger Reviewbefund und Koordinationsübergabe im Chief-of-Staff-Chat `01a18453-50f4-7463-a3a6-9a45c56297d7`.

Die konkreten Fälle betreffen vorhandene Zusagen: ein an Profil A gebundener Auftrag bei belegtem Account A darf einen späteren bereiten Claude-Auftrag nicht aushungern; ein ungepinnter Auftrag darf durch ein belegtes A nicht dauerhaft ein zulässiges freies B übersehen. Der Fix muss die Accountlocks respektieren, alle Quoten-/Modellbedingungen erhalten, angeheftete Profile beibehalten und bei bloßem Busy keinen Versuch verbrauchen. Der unabhängige Job über Claude ist keine Providerersetzung für den blockierten Auftrag.

Der Root-Koordinator wies dem ursprünglichen Python-/Skillchat kontrollierte Reproduktion, Korrektur, Tests und Review zu; der Rust-Verantwortliche übernimmt den gleichwertigen nativen Fix. Zum Eintrag lagen weder ein finaler Fixcommit noch ein abgeschlossener gemeinsamer Reproduktions-/Abnahmenachweis vor. Der Befund verfeinert die bestehende Verfügbarkeits-/Nichtaushungerungsgrenze und erweitert den Produktumfang nicht.

## Python-Lock-Vertrag geliefert: Checkpoint vom 2026-10-28

[PR #21](https://github.com/the-fin-at/agent-pool/pull/21) / [Issue #20](https://github.com/the-fin-at/agent-pool/issues/20) wurde auf `the-fin-at/agent-pool@ddbc859cbecb7c7af80fc2be918574d34d0099d7` gemergt; Implementierung `e0bae058c9df4af40766ec16fc0097058bd29fca`, finaler Quellbranchstand `b27267e`. Der [Routing-Vertrag](../docs/agent-routing-contract.md) ergänzt Punkt 11: Busy ist ein pro Tick begrenztes Überspringen des belegten Kandidaten. Der Job behält seinen Versuchszähler, Profilnutzung/Quoten/Holds bleiben durch Busy unverändert; ungepinnte Jobs können ein weiteres zulässiges same-provider Profil versuchen, gepinnte warten, spätere unabhängige Jobs dürfen fortschreiten. Lockhalter werden nicht beendet oder zwangsweise freigegeben. Damit ist der frühere offene Python-Fixstatus überholt; der native Rust-Nachweis bleibt getrennt.

Der direkt gelesene [Lock-Nachweis](../docs/native-lock-routing-validation.json) dokumentiert drei reproduzierte rote Fälle bei unverändertem Baseline-Worker und anschließend vier grüne Fälle mit echten temporären OS-Accountlocks, `run_native` und kontrollierten nativen Unterprozessen. Die vollständige Mac/Tk-Suite bestand 145 Tests ohne Skips; zwei unabhängige Reviews des Quellstands meldeten keine offenen Befunde. Diese Prüfungen änderten keine echten Account-/Quotendaten und wurden nicht auf dem produktiven Server ausgerollt. Eine zusätzliche Verifikation durch den ursprünglichen Befund-Reviewer wurde vom Root-Koordinator beauftragt; ihr Abschluss war bei diesem Eintrag noch nicht gemeldet.

## Zusätzlicher Gegencheck und spätere native Grenze: Checkpoint vom 2026-10-28

Der ursprüngliche Befund-Reviewer prüfte den gemergten Python-Fix bei `the-fin-at/agent-pool@ddbc859cbecb7c7af80fc2be918574d34d0099d7` zusätzlich: vier gezielte Tests und zwei Prüfungen mit getrennten Lockhalter-Prozessen bestanden. Beide Fortschrittsfälle funktionierten; der Lockhalter blieb am Leben und behielt den Lock. Busy auf A änderte weder Versuchszähler noch `last_used`, Quoten oder Holds. Es erfolgten keine Repo- oder Produktionsschreibzugriffe durch diesen Gegencheck. Damit ist die frühere offene Beobachtung über diesen zusätzlichen Python-Review überholt. Quelle: Review- und Statusmeldungen im Chief-of-Staff-Chat `01a18453-50f4-7463-a3a6-9a45c56297d7`.

Für Rust lag zusätzlich ein bestandenes unabhängiges Quell-/Testdesignreview der beobachteten Dateisnapshots vor: Worker-Hash `a8a3423ceee3`, Busy-Lock-Test-Hash `3e7bbaa7545b`, Kompatibilitätsprüfungs-Hash `fb606793d598`. Der begrenzte Umfang umfasste sechs Rust-Busy-Tests und zwei native Kompatibilitätsfälle; der Migrationsverantwortliche meldete erfolgreiche eigene Läufe. Es gab beim Checkpoint weiterhin keinen eingefrorenen finalen Commit mit abgeschlossener gemeinsamer Abnahme. Die Dateihashes binden das Review an vergängliche uncommitted Snapshots und ersetzen keinen Releasecommit.

Eine spätere Wiederholung des nativen Mac-WebView-Laufs endete trotz früherer gemeldeter Erfolge in einem Timeout. Der Kandidat wurde deshalb weder veröffentlicht noch abgenommen. Ein Mac-`.app`-Build war gemeldet; der DMG-Schritt über Finder lief ebenfalls in ein Timeout. Der gemeldete Distributionsstand war damit ein `.app`-Bundle, kein erfolgreich abgenommenes DMG. Frühere erfolgreiche native Teilprüfungen bleiben historische Beobachtungen und werden nicht still zu einem aktuellen finalen Pass erklärt. Quelle: jüngste Migrationschat-Kommentare „Entwirf einen CLI-Modellproxy“ (`01a18220-ca9a-7490-a64f-6cebc721d916`) und deren Statusübernahme im Chief-of-Staff-Chat am Erfassungstag.
