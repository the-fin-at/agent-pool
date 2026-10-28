# Aufträge und Integration

[Wiki-Index](index.md) · [Ziel](ziel.md) · [Entscheidungen](entscheidungen.md) · [Releaseplan](release-1.0.md)

## Koordinationsübernahme vom 2026-10-28

Johannes autorisierte die Koordination der beiden laufenden Chats. Der Chief of Staff sandte daraufhin beiden eine gemeinsame Integrationsvorgabe und getrennte Zuständigkeiten. Quelle: Chief-of-Staff-Chat `01a18453-50f4-7463-a3a6-9a45c56297d7`. Eine kompakte Statusabfrage zeigte beide letzten Turns noch als `inProgress`; vor weiterer Beauftragung ist das erneut zu prüfen.

| Arbeit | Verantwortlicher Quellchat | Beobachtung am 2026-10-28 | Nächste belegbare Übergabe |
| --- | --- | --- | --- |
| Rust-Kern, CLI, Tauri/React und Kompatibilität | „Entwirf einen CLI-Modellproxy“, `01a18220-ca9a-7490-a64f-6cebc721d916` | `feat/rust-tauri-migration`, Ausgangsbasis `f712523`, [Issue #12](https://github.com/the-fin-at/agent-pool/issues/12); noch keine vollständige Migrationsabnahme belegt | Kandidatencommit, jüngste main-Basis, Cross-Language-/Prozess-/UI-Belege, offene Grenzen |
| Quotenbewusste Profilwahl und Skills | „Entwirf einen CLI-Modellproxy (2)“, `01a1828a-6555-7313-98fd-3f715aa56c75` | `feat/quota-aware-agent-skill`, [Issue #14](https://github.com/the-fin-at/agent-pool/issues/14); fünf neue Routing-Vertragstests bestanden laut Chatbeobachtung, noch kein finaler Merge belegt | Finaler Commit/PR, Verhaltensvertrag, unabhängiges Review und Prüfbelege |
| Koordination, Integrationsrisiken und 1.0-Plan | Chief-of-Staff-Chat `01a18453-50f4-7463-a3a6-9a45c56297d7` | Wiki-Ort vom Nutzer bestätigt; beide Quellchats informiert | Plan an tatsächliche Abschlusscommits anpassen; einen gemeinsamen Kandidaten unabhängig prüfen |

Am 2026-10-28 gehörten `wiki/**` ausschließlich dem Wiki-Worker. Dieser legte keine Git-Stages oder Commits an. Technische Migrationsdocs blieben beim Migrationschat; der Skillchat sollte Rust-/Tauri- und Wiki-Dateien nicht bearbeiten. Änderungen anderer werden nicht zurückgesetzt.

Die beobachteten Aufgaben wurden über bestehende Codex-Chats geführt. Ihnen ist keine neue Fleet-Job-ID und kein Fleet-Schlüssel zugeordnet. Solche Werte dürfen nicht erfunden werden. Für später tatsächlich eingereichte Fleet-Jobs werden Ziel/Host, Job-ID, stabiler Schlüssel, `chosen_profile`, Ausgangs-/Ergebniscommit, Statuszeitpunkt und Ergebnisverweis ergänzt.

## Integrationsfolge, am 2026-10-28 festgelegt

1. Der Skillchat beendet seine begrenzte Arbeit mit belegtem Verhaltensvertrag und finalem Commit. Die Claude-Korrektur bleibt durch PR #13/`50e4297` referenziert.
2. Der Migrationschat übernimmt die dann jüngste gemeinsame main-Basis. Er belegt die Portierung des Verhaltens in Rust, statt nur Python-Dateien in den Branch zu übernehmen. Die finale Basis ist nachweislich Vorfahr des Kandidaten; Abweichungen werden vor Review aufgelöst.
3. Prüfungen laufen am gemeinsamen Kandidatencommit. Uncommitted Änderungen und Tests an unterschiedlichen Commits ergeben keine gemeinsame Abnahme. Ein neuer Commit nach Review braucht die davon betroffenen Prüfungen erneut.
4. Unabhängige Standards-/Spec-Prüfung bewertet genau diesen Kandidaten; die Spec-Prüfung umfasst die [Produktentscheidungen](entscheidungen.md) und [Release-Matrix](release-1.0.md).
5. Vor einer Installation: aktive Jobs und Prozesse beobachten; eigener Worker nur kontrolliert umstellen; native Logins und andere Dienste bewahren. Release-/Rollbackbelege gehören zum Paket und Commit.

## Wiederaufnahme und Konflikte

Am 2026-10-28 galt als Arbeitsregel: erst Quellchatstatus und tatsächliche Arbeitskopie prüfen, dann neue Arbeit planen. Änderungen an unterschiedlichen Strängen dürfen parallel laufen; Integration hat einen benannten Verantwortlichen und eine konkrete gemeinsame Basis. Ein blockierter Quellchat wird nicht durch einen ungeprüften Ersatzauftrag dupliziert.

Wenn ein laufender Prozess oder eine Schreibausführung unklar endet, folgt eine Bestandsaufnahme der Dateien, Prozessgruppen und Jobzustände vor jeder Wiederholung. Quotenwartezeit bleibt offene Arbeit. Ein veralteter Heartbeat allein beweist weder Ausführung noch Prozessende.

## Ergänzende Beobachtung vom 2026-10-28

Der Chief of Staff meldete nach dem Ersteintrag eine Erweiterung auf sieben bestandene Routing-Vertragstests im Profilwahl-Strang. Ein echter Auftrag ohne angeheftetes Profil wurde zusätzlich geprüft; zum Zeitpunkt dieser Übergabe war dessen Prüfung noch in Bearbeitung. Quelle: spätere Statusbeobachtung des Chief-of-Staff-Chats `01a18453-50f4-7463-a3a6-9a45c56297d7` zum Quellchat „Entwirf einen CLI-Modellproxy (2)“. Diese Beobachtung überholt die frühere Zahl von fünf Tests in der Tabelle für den Fortschritt des Strangs, nicht den fehlenden finalen Merge-/Integrationsnachweis. Ein bestandenes Live-Ergebnis wird daraus nicht abgeleitet.

## Verifizierter Abschluss des Profilwahl-Strangs am 2026-10-28

[PR #15](https://github.com/the-fin-at/agent-pool/pull/15) ist gemergt. `main` und der lokale `origin/main`-Verweis wurden bei `3c9d7faf53025a1271f6ad65e2ea4a0c25e9e548` geprüft. Der [Routing-Vertrag](../docs/agent-routing-contract.md) und [JSON-Nachweis](../docs/agent-routing-validation.json) belegen 141 Mac/Tk-Tests, sieben isolierte echte Linux-Routingtests, unabhängige Standards-/Spec-Reviews ohne offene Befunde und einen echten ungepinnten Codex-Job mit automatischer Profilwahl und genau einem erfolgreichen Versuch. Damit sind die früheren offenen Beobachtungen zur Profilwahl und zum noch laufenden ungepinnten Live-Test überholt. Die Erschöpfungs-/Failoverfälle wurden ausschließlich isoliert geprüft; die reale Poolquote blieb unverfälscht.

Der Chief of Staff meldete dem Migrationschat den Mergecommit und Verhaltensvertrag. Die zuletzt beobachtete Migrationsbasis enthielt bereits `50e4297`; die Integration von `3c9d7fa` als Vorfahr eines finalen Migrationskandidaten war beim Checkpoint noch nicht belegt. Nächster Schritt ist deshalb die Übernahme dieses finalen gemeinsamen Stands und die äquivalente Rust-Abnahme, nicht eine neue Profilwahl-Implementierung im abgeschlossenen Python-Strang. Die ursprüngliche Zuständigkeit des Migrationschats bleibt bestehen.
