# Releaseplan Agent Fleet 1.0

[Wiki-Index](index.md) · [Zielauftrag](ziel.md) · [Produktentscheidungen](entscheidungen.md) · [Aufträge](auftraege.md)

## Planentscheidung vom 2026-10-28

Die Reihenfolge folgt dem Risiko: erst dieselbe Funktion auf gemeinsamer Basis, dann Fehlergrenzen und native Pakete, schließlich eine reproduzierbare Releaseentscheidung. Die folgende Planung fügt keine neuen Produktbereiche hinzu. Datenbank, CLI/RPC, native Accounts, Quotensteuerung und Desktop-Übersicht sind der Prüfgegenstand. Ausgangsbelege: `the-fin-at/agent-pool@50e4297`, [Live-Account-Abnahme](../docs/live-account-validation.md), [Realhost-Methode](../docs/claw-remote-validation.md), Migrationsspezifikation des [Issue #12](https://github.com/the-fin-at/agent-pool/issues/12).

| Etappe | Ergebnis und Abhängigkeit | Nachweis zum Verlassen der Etappe |
| --- | --- | --- |
| Integration / 0.5-Kandidat | Rust/Tauri übernimmt finalen Claude- und Profilwahl-Stand; abhängig vom Abschluss beider [Quellaufträge](auftraege.md) | Gemeinsamer Commit; Format/Lint/Build/Tests grün; kompatible Daten und RPC; unabhängiges Review |
| Stabilisierung vor 1.0 | Derselbe Kandidat besteht Restart-, Quoten-, SSH- und Zustandsprüfungen, ohne bestehenden produktiven Pool für Fehlerfälle zu verwenden | Pro Szenario Commit, Host, Eingaben, Beobachtung, Ergebnis und Artefakt; rote Fälle behoben und erneut geprüft |
| Native Auslieferung | Reproduzierbare macOS-App, Linux-CLI/Worker und Windows-Desktop/CLI innerhalb des angekündigten Supports | Installation/Upgrade/Rücknahme auf nativen Zielsystemen; Paketchecksummen; externe Laufzeitabhängigkeiten explizit |
| 1.0-Abnahme | Umfang, Plattformunterstützung, Paket und Belege stimmen überein | Pflichtmatrix grün, kein offener blockierender Befund, Dokumentation und Skills zum Kandidaten passend; bewusste Releaseentscheidung |

Eine native Windows-Prüfung bleibt Pflicht für eine als Mac-und-Windows unterstützte 1.0. Ohne Zugang lässt sich der Kandidat weiter prüfen, aber dieser Support nicht als abgenommen bezeichnen. Fehlende GitHub-CI darf nicht durch eine Formulierung „alles grün“ verschwinden.

## Harte Ziele, am 2026-10-28 als Abnahmemaßstab festgelegt

- **Identität und Bestand:** In einer eingefrorenen alten Testdatenbank bleiben 100 % der aufgeführten Profil-/Job-IDs, Ergebnisse, Zustände, Auth-Pfadzuordnungen und Remote-Konfigurationen erhalten; SQLite-Integritätsprüfung erfolgreich. Keine Zugangsdaten werden kopiert.
- **Einreichung:** 16 gleichzeitige identische Einreichungen und erneute Einreichung nach verlorener Antwort liefern genau dieselbe Job-ID/einen Datensatz; anderer Inhalt unter demselben Schlüssel wird zurückgewiesen.
- **Ausführung:** Ein isolierter Lauf von mindestens 100 deterministischen kontrollierten Jobs ohne induzierte Wiederholung hat 100 erhaltene Ergebnisse, keine verlorenen Jobs, keine doppelte native Ausführung. Erzwungene Retries werden als eigene Versuche derselben Job-ID sichtbar.
- **Unklare Ausführung:** Unterbrechung/Timeout hinterlässt keinen aktiven kontrollierten Kindprozess; ungewisse Arbeit erreicht `needs_review` und wird nach Neustart nicht still erneut ausgeführt. Das ist keine Zusage von Exactly-once für externe Nebenwirkungen. Ein Prozess kann vor einem Quoten-/Transportfehler bereits Wirkung gehabt haben; die gewählte Retry-Politik muss diesen Fall prüfen und sichtbar machen.
- **Quoten:** In jedem Matrixfall wird nur ein zulässiges Profil gewählt; kein Provider-/Modellwechsel außerhalb des Auftrags. Ausgeschöpfte Woche/Modellfenster bleiben wirksam, auch wenn das 5h-Fenster frei wird. Unbekannte Resets erzeugen keine erfundenen Startzeiten.
- **Reaktionsfähigkeit:** Bei 2 s künstlicher Transportverzögerung erreicht die native Oberfläche Eventloop-p95 < 100 ms, Maximum < 500 ms; 20 echte SSH-Statusmessungen erreichen p95 < 3 s. Das übernimmt die nachgewiesenen 0.4.1-Ziele, nicht deren Ergebnis für Rust. Broker-Durchsatz wird getrennt von Modellinferenz gemessen.

## Pflichtmatrix für den gemeinsamen Kandidaten

Jede Zeile erhält einen tatsächlichen Prüfbefehl bzw. Ablauf, Kandidatencommit, Host, Resultat und Artefaktverweis. Die Tabelle ist ein Prüfauftrag, kein Testbericht.

| Bereich | Prüfverfahren und Randfälle | Bestehende Quellen / geplanter Richter |
| --- | --- | --- |
| Basisqualität | Cargo fmt/check/clippy/tests; Frontend-Typecheck/Build/Tests; Python-Regressionssuite | Migrationsspec, CI-/lokale Logs genau desselben Kandidaten |
| Python ↔ Rust | Python erzeugt alte DB; Rust liest/ändert; Python liest zurück; IDs/Reports/Status/Auth-Pfade vergleichen; Schema-/Integritätscheck | Versionsfixierte isolierte Fixtures und unabhängige Dateninventur |
| Gemeinsame Locks | Python/Rust-Worker und Login verwenden dieselben Lease-/Accountlocks; zweiter Prozess führt nicht parallel aus | Echte OS-Prozesse, PIDs, Lease-/Jobzustände |
| Claude-Limits | Real sanitisiertes `unifiedWindows`, Legacy, 5h/Woche/Modell, Reset-Aliasse, Overage; CLI → Cache → Rust-UI | [Originalfixture](../tests/fixtures/claude-unified-limits.json), PR #13; Wertevergleich |
| Profilwahl vor Start | 5h voll → anderes Profil; Woche/Modell blockieren trotz freiem 5h; deaktiviert/belegt/Fehlerprofil; unbekannte/stale Werte; explizites Profil bleibt angeheftet | Python-Routingvertrag und äquivalente Rust-Vertragstests; kein bloßes File-Review |
| Runtime-Quota | Gleiche Job-ID und sichtbare Versuche; anderer zulässiger Account; Nebenwirkungs-/Unklarheitsfall gesondert; keine unautorisierte Providerrotation | Kontrollierter Provider mit Ausführungsmarker und Job-/Versuchsinventur |
| Alle Profile gesperrt | Kein Busy-Loop, passende nächste Freigabe über alle Fenster; unbekannter Reset sichtbar; anderer Providerjob wird nicht unnötig ausgehungert | Virtuelle Zeit wo geeignet und echte Worker-Reaktivität |
| SSH/RPC | Python0.4.x ↔ Rust-RPCv1 soweit zugesagt; Antwortverlust, identischer Retry, Requestgrenzen, literal Unicode/Shelltext, ungültige Requests | [Remote-Vertragstests](../tests/test_remote.py), isolierter Realhost-Testpool |
| Restart/Timeout | Beenden während nativem Prozess, Kindprozessgruppen prüfen, `needs_review`, manuelle Retry-Bestätigung, kein Replay | [Prozesstests](../tests/test_processes.py), Realhost-Fehlerloop |
| Native Login/UI | Codex/Claude Start/Input/Cancel; Kontextwechsel, verspätete Antworten, Fehler und unbekannte Quoten; Übersicht/Login ohne neue Desktop-Jobvergabe | Echte Tauri-Fenster und kontrollierte Provider; menschliche Provider-Zustimmung bleibt ausdrücklich getrennt |
| Paket und Upgrade | Alte State-Pfade; bestehende Daten lesbar; gebündelter Rust-Runtimepfad ohne Python; native CLI-Discovery; Start aus installiertem Paket | macOS und Windows nativ, Linux CLI/Worker; Checksummen und Versionsvergleich |
| Betrieb/Rollback | Neue Claims anhalten; aktive Ausführungen beenden/abwarten oder bei Unklarheit als `needs_review` erhalten; queued/waiting-Jobs samt IDs/Ergebnissen bewahren; Datenbackup kompatibel; letzte funktionierende Version gezielt wieder starten; keine Credential-Kopien oder verlorenen Fremddienste/Logins | Kontrollierte Übergabe und tatsächlicher Restart/Rollback mit noch wartenden Jobs in einem isolierten Pool |
| Review/Docs | Exakten Commit gegen Anforderungen/Standards prüfen; README, Skills, CLI-Hilfe und Paket gleichziehen; alte Nachweise als historisch markieren | Unabhängige Reviewer plus Link-/Paket-/Versionsprüfung |

## Ergänzende Integrationsbeobachtung vom 2026-10-28

Der unabhängige Integrationsaudit beobachtete im noch uncommitted Migrationsworktree auf Basis `f712523` eine wichtige Prüflücke: bisherige Rust-Providerfixtures deckten das äußere Legacy-Claude-Fenster ab, nicht den späteren `unifiedWindows`-Regressionsvertrag. Deshalb ist die Zeile „Claude-Limits“ am tatsächlichen Rust-Job und den gespeicherten Fenstern zu belegen. Die Beobachtung ist ein Übergabehinweis an den Migrationsverantwortlichen, kein Befund gegen einen noch nicht existierenden finalen Kandidaten.

Die vorhandene [native Desktop-Prüfung](../scripts/test_real_host_desktop.py) prüft die Python/Tk-App. Der [Realhost-Serverloop](../tests/real-host/server_checks.py) wurde für das Python-Archiv geschrieben. Ihre alten grünen Ergebnisse ersetzen keine Tauri-/Rust-Abnahme; die passenden öffentlichen Grenzen müssen gegen den nativen Kandidaten ausgeführt werden. Die Integration/0.5-Abnahme und die weitergehenden Plattform-/Vertriebsgates für 1.0 bleiben getrennt. Windows- oder öffentliche Signierungsnachweise werden nicht rückwirkend zu einer Behauptung über die bereits erfolgte 0.4.2-Abnahme.

Die unabhängige Wiki-Prüfung korrigierte am 2026-10-28 die frühe Planforderung „Keine offenen produktiven Jobs bei eigenem Workerwechsel“. Diese Formulierung ist überholt: Sie könnte ein Leeren der Queue einschließlich quotenwartender Jobs verlangen. Der Nachfolger ist eine kontrollierte Prozessübergabe unter Erhalt wartender Jobs; Restart und Rollback werden mit ausstehender isolierter Arbeit bewiesen. Die Matrix enthält diesen präzisierten Vertrag.

## Zugriff und Nachweislücken, beobachtet am 2026-10-28

| Voraussetzung | Belegter Zugang / Grenze | Wirkung auf den Plan |
| --- | --- | --- |
| Quellen und Tests | Lokale Python-Quelle bei `50e4297`, aktiver Rust-Worktree; native Quotenfixtures und isolierte Realhost-Runbooks vorhanden | Integration und Cross-Language-/Fehlertests können vorbereitet und ausgeführt werden |
| macOS und Linux | Historische echte Mac-/`claw-remote`-Belege in den verlinkten Abnahmen; aktive Zugänge vor erneutem Einsatz verifizieren | Neue Rust-Abnahme separat durchführen; ältere Python-Ergebnisse nicht übernehmen |
| Windows | Native Abnahme laut 0.4.2-Nachweis noch offen; verfügbare Maschine/Runner nicht belegt | Native Installation/Login/Prozess-/UI-Prüfungen vor Windows-Supportfreigabe beschaffen |
| GitHub-CI | Historisch bekannte Billing-Sperre, kein grüner CI-Nachweis | Runnerzugang vor Release verifizieren; Billingänderung nicht still im Plan ausführen |
| Signierung | Für bisheriges Python-Mac-Paket Ad-hoc-Signatur belegt; Tauri Developer-ID/Notarisierung und Windows-Signierung nicht belegt | Gewählten Vertriebsweg und tatsächliche Zertifikats-/Notarisierungsprüfung vor Veröffentlichung klären; keine vorhandene Signierung erfinden |
| Browserzustimmung | Bestehende Accounts nachgewiesen; neue Anbieterzustimmung ist menschlicher Schritt | Bestehende Auth-Daten erhalten; nicht automatisierbare Zustimmung als echte Abnahmegrenze melden |

## Releaseentscheidung und Fortschreibung

Am 2026-10-28 wurde als Regel festgelegt: Etappe, Kandidatencommit, Testhost, kontrollierter Provider versus echte Inferenz, Paketchecksumme und Reviewstand werden gemeinsam festgehalten. Ein neuer technischer Commit entwertet betroffene frühere Prüfungen, nicht zwingend alle unabhängigen Belege. Es wird kein Release als 1.0 abgenommen, solange eine Pflichtgrenze unbewiesen oder ein blockierender Befund offen ist. Spätere Resultate ergänzen diesen Plan als datierte Ereignisse in der [Auftragsübersicht](auftraege.md) und präzisieren betroffene Seiten samt [Index](index.md).

## Fortschrittscheckpoint vom 2026-10-28: gemeinsame Basis steht bereit

Die Profilwahl-/Skill-Abhängigkeit der ersten Etappe ist mit [PR #15](https://github.com/the-fin-at/agent-pool/pull/15) abgeschlossen. Lokal geprüft wurden `main` und `origin/main` bei `the-fin-at/agent-pool@3c9d7faf53025a1271f6ad65e2ea4a0c25e9e548`. Für den Python-/Skill-Stand liefern [Vertrag](../docs/agent-routing-contract.md) und [normalisierte Belege](../docs/agent-routing-validation.json) 141 Mac/Tk-Tests, sieben isolierte Routingtests auf echtem Linux, unabhängige Reviews und einen erfolgreichen echten ungepinnten Codex-Auftrag in einem Versuch. Dieser Live-Auftrag beweist nicht den Wechsel nach realer Erschöpfung; dessen Verhalten wurde isoliert geprüft.

Der nächste belegbare Schritt bleibt ein Rust-Kandidat mit `3c9d7fa` als gemeinsamer Vorgänger und gleichwertigen Quoten-/Profilwahlprüfungen. Die letzte beobachtete Migrationsbasis `50e4297` reicht für diesen jüngeren Profilwahl-Vertrag allein nicht aus. Die Quellchatmeldung, Claude-Korrekturen seien übernommen und Rust/DB/Tauri würden getrennt abgenommen, wird erst durch den Kandidatencommit und seine Belege zur gemeinsamen Abnahme. Keine Zeile der Pflichtmatrix wird allein durch diesen Plancheckpoint als grün markiert.

## Ergänzter Zielvertrag und Prüfstand vom 2026-10-28

Die spätere [Nutzerkorrektur](entscheidungen.md) ergänzt die Pflichtmatrix: Zielwahl wird pro Projekt geprüft, nicht aus einem globalen persönlichen Standardziel abgeleitet. Neue Fälle sind Projekt A mit lokalem Ziel und Projekt B mit ausdrücklichem Remote-Ziel, unveränderliche Zuordnung während laufender Arbeit, expliziter Nutzerwechsel sowie fehlende Zuordnung ohne stillen Fallback oder neue Einreichung. Maschinenlokale Auth-/Hostparameter bleiben dabei erhalten. Der aktive Fix-Strang `fix/project-scoped-execution-target` war beim Checkpoint noch nicht final gemergt; die Erfüllung dieses Vertrags bleibt bis zum Kandidatenbeleg offen.

Die [Auftragsübersicht](auftraege.md) ergänzt PR #16/`d09c623` und den separaten kontrollierten Python-Nachweis: Schreibfehler/Quota führt zu `needs_review` ohne Replay über Profil B; read-only Quota behält dieselbe Job-ID/denselben Schlüssel und nutzt Profil B im zweiten Versuch; 43 Python-Tests bestanden. Dieser Nachweis präzisiert das Referenzverhalten für Rust. Er ersetzt keine Rust-, native UI-, Windows- oder Paketprüfung und markiert kein solches Gate als bestanden.

## Finaler Projektziel-Checkpoint vom 2026-10-28

[PR #18](https://github.com/the-fin-at/agent-pool/pull/18) liefert auf `the-fin-at/agent-pool@2d7774cad132a542cdf99c8eaf7b3b4567794d90` den korrigierten Projektziel-Vertrag. Die offene Fix-Strang-Beobachtung im vorigen Eintrag ist dadurch überholt. [Projektziel-Anleitung](../skills/agent-fleet/references/project-target.md) und [Korrektur-Nachweis](../docs/project-target-validation.json) unterscheiden die tatsächlichen Prüfgrenzen: sieben isolierte Routingtests, ein Installationstest, Validatoren und Hash-/Policyprüfungen sowie unabhängige Entscheidungsszenarien; keine neue echte Inferenz und kein neues Runtime-Projektschema. Hosted CI blieb nachweislich vor Teststart wegen Billing blockiert.

Die erste Release-Etappe hat damit einen finalen gemeinsamen Python-/Skill-Ausgangspunkt inklusive Claude-, Profilwahl- und Projektzielkorrektur. Der gemeinsame Checkout wurde sauber auf `2d7774c` gebracht, siehe [Auftragsübersicht](auftraege.md). Die Übernahme und Prüfung in Rust bleibt Pflicht: ein Kandidat mit diesem Commit als Vorfahr, übereinstimmendem Verhalten und eigenständigen Rust-/DB-/Tauri-Nachweisen. Ein erfolgreicher Wiki-/Skillabschluss wird nicht als bestandenes Rust-Gate verbucht.

## Konkreter Nichtaushungerungsfall vom 2026-10-28

Der [unabhängige Scheduling-Befund](entscheidungen.md) konkretisiert die bereits vorhandenen Matrixzeilen „Gemeinsame Locks“, „Profilwahl vor Start“ und „Alle Profile gesperrt“: (1) nativer Lock auf angeheftetem Profil A, danach unabhängiger bereiter Claude-Job; (2) ungepinnter Auftrag mit belegtem A und zulässigem freiem Profil B. Kontrollierte native Prozesse sollen den Lock tatsächlich halten. Bestanden bedeutet Fortschritt der zulässigen Arbeit ohne Umgehung des Locks, ohne verlorene Profilpins oder Quotenbedingungen und ohne Versuchszählerverbrauch für Busy. Die Reihenfolge geeigneter unabhängiger Jobs und die Nachweise der ausgeführten Profile müssen beobachtet werden; ein bloßer erfolgreicher Build reicht nicht.

Der Python-/Skill-Verantwortliche bearbeitet Reproduktion und Referenzfix, der Rust-Verantwortliche die native Entsprechung; siehe [Auftragsübersicht](auftraege.md). Der neue Fix war beim Eintrag noch nicht abgeschlossen. Der Rust-Bericht über Core-/CLI-Kompilierung und Frontendtests/-build belegt Teilprüfungen; die native Kompatibilitäts-/Tauri-Abnahme bleibt offen. Die finale gemeinsame Basis muss auch den nachgewiesenen Busy-Fix enthalten, sobald dessen Commit vorliegt. Das ergänzt einen bestehenden Zuverlässigkeitsvertrag, keine neue 1.0-Funktion.

## Referenzfix für native Lock-Auswahl: Checkpoint vom 2026-10-28

Der Python-Teil des zuvor konkretisierten Busy-/Nichtaushungerungsfalls wurde mit [PR #21](https://github.com/the-fin-at/agent-pool/pull/21) auf `the-fin-at/agent-pool@ddbc859cbecb7c7af80fc2be918574d34d0099d7` abgeschlossen. [Routing-Vertrag Punkt 11](../docs/agent-routing-contract.md) und [Lock-Nachweis](../docs/native-lock-routing-validation.json) liefern den jetzt maßgeblichen Referenzvertrag samt vier Fällen mit tatsächlich gehaltenen temporären Locks und kontrollierten Unterprozessen sowie 145 Mac/Tk-Tests. Die produktive Linux-Runtime wurde nicht aktualisiert; Hosted CI blieb vom lokalen Nachweis getrennt.

Die nächste integrierte Abnahme benötigt `ddbc859` als gemeinsame technische Basis und gleichwertige Rust-Fälle. Gemeldete 18 native Kompatibilitätsfälle und echte Tauri-Mac-Teilprüfungen sind wertvolle zusätzliche Belege, gelten jedoch noch nicht für den neuen Busy-Fix auf einem eingefrorenen Kandidaten. Zusätzlicher Python-Gegencheck, finaler Rust-Commit, native Lock-Reproduktion und die bereits festgelegten weiteren Gates bleiben voneinander getrennte Prüfpunkte. Kein Windows- oder endgültiges Release-Gate wird durch diesen Zwischenstand als bestanden markiert.

## Aktualisierte offene Abnahmegrenzen vom 2026-10-28

Der zusätzliche unabhängige Python-Gegencheck am gemergten `ddbc859` bestand einschließlich vier gezielter Tests und zweier separater Lockhalter-Prozessfälle. Die in [Entscheidungen](entscheidungen.md) gebundenen Rust-Busy-Dateisnapshots bestanden ein begrenztes Quell-/Testdesignreview; gemeldete eigene native Testläufe bleiben ohne eingefrorenen finalen Kandidaten ergänzende Belege.

Die spätere wiederholte Mac-WebView-Prüfung endete im Timeout. Damit wäre die Annahme „nur noch Linux offen“ überholt: native Mac-Start-/IPC-Diagnose und erneute Kandidatenprüfung sind ebenfalls offen. Der `.app`-Build allein erfüllt kein Start-/UI-Gate; ein im Finder-Schritt hängender DMG-Bau ist kein abgenommenes DMG. Der Kandidat wurde nicht veröffentlicht oder final akzeptiert. Die [Auftragsübersicht](auftraege.md) benennt Diagnose- und Prüfverantwortliche.

Die isolierte Linux-Quellübertragung wurde automatisch abgelehnt; direkte Nutzerzustimmung ist im ursprünglichen Migrationschat offen. Ohne sie wird weder derselbe Transfer noch ein alternativer Exportweg ausgeführt. Lokale Prüfungen können unabhängig weiterlaufen. Das ist eine konkret benannte Zugangsgrenze, kein ersatzweise bestandener Linux-Test. Es gab keine produktive Serveraktualisierung und keinen neuen Windows-Nachweis.

## Aufgelöste Zugangsgrenzen und neue konkrete Reviewgates: 2026-10-28

Nach direkter Nutzerfreigabe bestanden auf dem echten Linux-Host 22 native Fälle und 100 eindeutige kontrollierte Jobs/Ausführungen. Ein unabhängiger tatsächlicher SSH-Antwortverlust mit identischem Retry erzeugte genau einen Job. [Entscheidungen](entscheidungen.md) binden diese Belege an Binärhash, Build-/Ausführungsorte und das ausdrücklich nicht final eingefrorene Quellsnapshot. Sie ersetzen nicht die Zuordnung des zuletzt veränderten Releasepakets zu seinem endgültigen Commit. Produktionsdienst und Auth-Zustand wurden nicht aktualisiert.

Die spätere falsche Mac-Console-Vorprüfung wurde im Helfer von `131278b` korrigiert; eine frühere reale Bildschirmsperre wird damit nicht als falsch umgedeutet. Ein historischer 23-Schritt-WKWebView-/Rust-IPC-Nachweis ist anhand der tatsächlichen Artefakte bestätigt, aber ausdrücklich kein neuer Lauf für den inzwischen weiterbearbeiteten Kandidaten. Der nächste Kandidat benötigt vor Akzeptanz die betroffenen Regressionen und Wiederholungsprüfungen für den Connection-Dialog mit verspäteter Save-Antwort sowie die Unterscheidung von Dateisystem-Lockfehler und echtem Busy. Danach folgt erneutes Zwei-Achsen-Review auf genau diesem Stand.

Damit sind neue reale Belege und die gezielte Freigabe vorhanden, während der gemeinsame Endkandidat weiterhin offen bleibt. Windows und finale Paket-/Vertriebsnachweise sind separate Gates; der bisherige `.app`-Befund wird nicht zu einem DMG-Pass erweitert. Weitere Arbeit folgt diesen konkreten Abnahmerisiken, nicht zusätzlichen Produktfunktionen.

## Integration/0.5 abgeschlossen: Checkpoint vom 2026-10-28

Die erste Etappe dieses Plans ist durch [PR #22](https://github.com/the-fin-at/agent-pool/pull/22), `the-fin-at/agent-pool@9f018a1ff90f9da0b8fba1a90e3ee02c67e142f7`, abgeschlossen. Der Code-/Reviewstand `c47144087d3d7f665600ef0183af1c94dcd5180d` basiert auf `ddbc859` und enthält Claude-Fenster, automatische Profilwahl, Projektzielvertrag und native Busy-Fortschritte. Beide späteren P2-Fälle wurden korrigiert, mit Regressionen geprüft und ohne offene Standards-/Spec-Befunde erneut bewertet. Nach `c471440` folgten nur Nachweise und die native Aufnahme.

[Finale Abnahmedaten](../docs/rust-tauri-validation.json) und [Review](../docs/reviews/rust-tauri-review.md) belegen 145 Python-/Tk-, 85 Rust-Kern-, zwei Bridge- und 22 React-Tests sowie Format/Clippy/Typprüfung/Build. Je 23 Cross-Language-/Prozessfälle und je 100 eindeutige kontrollierte Jobs/Ausführungen bestanden auf Mac, lokalem Linux-Container und echtem isoliertem Linux. Die tatsächliche Mac-WKWebView-/Rust-IPC-Prüfung bestand 23 Schritte am finalen Stand. Der unveränderte Python-0.4.2-Server blieb kompatibel, sieben vorhandene IDs und ein Bericht erhalten. Das schließt die frühere gemeinsame Kandidatenlücke; es macht kontrollierte Provider weder zu echter Modellinferenz noch einen Build oder Debug-UI-Lauf zum vollständigen Vertriebsnachweis.

Mac-CLI und `.app` 0.5.0 sind anhand ihrer installierten Releasehashes geprüft. Der produktive Linux-Worker wurde nicht auf Rust umgestellt. Windows wurde nicht nativ ausgeführt, gehostete CI nicht gestartet, öffentliche Notarisierung nicht erbracht. Die Paketform ist `.app`; ein erfolgreiches DMG wird nicht behauptet. Damit ist 0.5 integriert und geprüft, während 1.0 weiterhin die folgenden konkret priorisierten Nachweise benötigt.

## Nächste 1.0-Schritte nach der Integration, geplant am 2026-10-28

| Priorität / Abhängigkeit | Nächster begrenzter Auftrag | Unabhängiges Pass-Kriterium |
| --- | --- | --- |
| P0: Plattformzugang | Native Windows-Maschine oder tatsächlich startenden Runner bereitstellen; vorhandenen NSIS-/CLI-Pfad dort prüfen | Installation/Start, Login/Abbruch, Quotenanzeige, CLI, Prozessgruppen/Timeout und Daten-Upgrade nativ ausgeführt; keine Übernahme von Mac-/Linux-Skips als Windows-Pass |
| P0: gehostete Releaseprüfung | Zuständigen Billing-/Runnerzugang klären und dann die bestehende native/Referenzmatrix auf genau dem Releasecommit ausführen | Jobs laufen tatsächlich; Resultate und Artefakte zum Commit archiviert. Keine Regelabschwächung oder eigenmächtige Billingausgabe |
| P0: Upgrade und Rücknahme | Kontrollierte Übergabe des bestehenden Poolformats einschließlich queued/waiting-/`needs_review`-Arbeit und Rücknahme in isoliertem Bestand beweisen; produktiven Serverwechsel separat planen | Neue Claims kontrolliert stoppen, aktive Arbeit beenden/prüfen, IDs/Ergebnisse/Logins erhalten; Restart und Rollback mit ausstehenden Jobs geprüft, kein stiller Replay und keine Credential-Kopie |
| P1: Performanceziele | Vorhandene Status-/UI-Latenzziele am nativen gemeinsamen Kandidaten messen; Quoten-/Lock-/Transportfehler dabei beobachten | Echte SSH-Statusmessung p95 < 3 s; UI bei 2 s Transportverzögerung p95 < 100 ms/max < 500 ms; Messhost/Commit/Verteilung dokumentiert. Bereits grüne 100-Job-Last ersetzt diese Latenzmessung nicht |
| P1: Vertriebsweg und reproduzierbare Pakete | Privaten oder öffentlichen 1.0-Vertrieb ausdrücklich festlegen; benötigte Mac-/Windows-Signierung und gegebenenfalls Notarisierung mit realem Zugang nachweisen | Installierbare Pakete und Prüfsummen stimmen mit dem geprüften Commit überein; gewählter Vertriebsweg, Signierstatus und Upgrade/Rücknahme sind reproduzierbar dokumentiert |
| Abschluss nach Pflichtgates | 1.0-Scope, unterstützte Plattformen, README/Skills/Hilfe, Paket-/Installationsbelege und Review zusammen prüfen | Kein offener blockierender Befund und keine unbewiesene als unterstützt angekündigte Pflichtgrenze; eine begründete separate 1.0-Releaseentscheidung |

Diese Tabelle plant die nächsten Schritte und startet weder eine Servermigration noch neue Infrastruktur, Billingänderungen oder zusätzliche Produktfunktionen. Fehlender Zugang bleibt konkret sichtbar; unabhängige lokale Prüfungen können weitergehen. Quellen und vollständige 0.5-Grenzen stehen in [Migrationsdokumentation](../docs/rust-migration.md), [Abnahmedaten](../docs/rust-tauri-validation.json) und [Auftragsübersicht](auftraege.md).

## Produktions- und Adaptergate nachgezogen: Checkpoint vom 2026-10-29

Der spätere direkte Auftrag führte den bestehenden produktiven Linux-Pool auf den geprüften nativen 0.5.0-ELF um; alle sieben alten vollständigen Jobs, sechs Profile/vier aktivierte Accounts, Auth-Verzeichnisse, Workspaces und die Unit blieben erhalten. Live-SQLite und eine konsistente Sicherung bestanden den unabhängigen Postcheck. Die bisherigen offenen Aussagen über den ausschließlich isolierten Rust-Testbetrieb und noch ausstehenden Produktionswechsel sind für diesen späteren Zeitpunkt überholt. [Betriebsrunbook](../docs/production-upgrade-2026-10-29.md) und [normalisierte Provenienz](../docs/production-upgrade-2026-10-29-validation.json) trennen den frühen Guard-Abbruch vom erfolgreichen Wechsel.

Anschließend bestanden zwei echte native read-only Providerjobs in je einem Versuch. Der dokumentierte Poolstand nach diesen Smokes ist neun erfolgreiche Jobs: sieben unveränderte alte plus zwei neue. Reale Adapter, Dateierwartung, unveränderte Fixtures und beendete Kindprozesse sind belegt; konkrete aufgelöste Modellnamen waren nicht sichtbar. Die beobachteten Queue-plus-Ausführungszeiten von 13,027/17,872 s sind Einzel-Smokes, keine Performance-Gate-Erfüllung. [Provider-Nachweis](../docs/native-provider-smokes-validation.json).

Die 1.0-Prioritäten werden dadurch präzisiert: Der tatsächliche Produktionswechsel ist belegt; die vollständige befüllte isolierte Upgrade-/Rollbackfehlerkampagne ([Issue #24](https://github.com/the-fin-at/agent-pool/issues/24)) und native Status-/UI-Performancegates ([Issue #25](https://github.com/the-fin-at/agent-pool/issues/25)) sind in Umsetzung und noch nicht als bestanden gemeldet. Die programmbezogene Rücknahme muss aktuelle Live-Daten einschließlich neuer Ankünfte erhalten; der alte Sieben-Job-Snapshot darf nicht zurückgespielt werden.

Johannes verfügte noch über keine Windows-Maschine und beauftragte ausdrücklich, die übrigen Gates weiterzuarbeiten. Windows bleibt daher zeitlich zurückgestellt/offen statt gestrichen oder ersatzweise abgenommen. Hosted CI blieb vor Start durch Billing blockiert; es wurde kein Self-hosted-Runner bereitgestellt. Vertriebs-/Signierungsgates und eine getrennte 1.0-Releaseentscheidung bleiben offen. Zusätzliche Produktfunktionen werden aus diesem Checkpoint nicht abgeleitet.

## Fortschreibung nach Übergabe- und Paketabnahme: 2026-10-29

Bezug: gemeinsamer Repository-Stand `the-fin-at/agent-pool@9a3bda9d55a92e8f5c7904d71ed6dcd3be0afce5`; nativer Produktcode unverändert bei `c47144087d3d7f665600ef0183af1c94dcd5180d`, Produktmerge `9f018a1ff90f9da0b8fba1a90e3ee02c67e142f7`. Die offenen Meldungen vom vorigen Checkpoint werden durch folgende abgegrenzte Resultate ergänzt.

| Gate / Status am 29.10.2026 | Nachweis und nächster notwendiger Schritt |
| --- | --- |
| Produktiver Linux-Wechsel / abgeschlossen | [PR #28](https://github.com/the-fin-at/agent-pool/pull/28), Merge `d4c893688e6fdcef44b1f8b0f6418ebcb52e8649`; erhaltene sieben alte Jobs und sechs Profile, unabhängiger Postcheck, zwei echte begrenzte Provider-Smokes. [Betriebsnachweis](../docs/production-upgrade-2026-10-29-validation.json) |
| Befüllte isolierte Pending-Übergabe / bestanden | [PR #26](https://github.com/the-fin-at/agent-pool/pull/26), Merge `f58e742ca362368b3c6bcce5a35670e06bff7304`: echtes altes Programm ↔ natives Programm, 30 Prüfungen, ID-/Ergebnis-/Auth-Sentinel-/Lease-Erhalt; programmbezogene Rücknahme ohne DB-Restore. [Nachweis](../docs/native-upgrade-rollback-validation.json) |
| Zwei aktive kontrollierte Übergabekanten / bestanden im benannten Umfang | [PR #32](https://github.com/the-fin-at/agent-pool/pull/32), Merge `9a3bda9d55a92e8f5c7904d71ed6dcd3be0afce5`: altes→natives WAIT und natives→altes INTERRUPT, 30 Prüfungen; Teilwirkung/Kindprozess beobachtet, `needs_review` ohne Replay erhalten, unabhängige Reviews. [Aktiver Nachweis](../docs/native-upgrade-rollback-active-validation.json). Kein atomarer Pausevertrag, kein konkurrierender Admin, keine symmetrische Vier-Kanten- oder systemd-Abnahme; Produktionswechsel separat belegt |
| Mac-/Linux-Paketierung / bestanden für dieselben geprüften Programme | [PR #30](https://github.com/the-fin-at/agent-pool/pull/30), Merge `cbc73174280b51ba373fcdce276c262d37f242bc`: echte Archive zweimal je Host identisch, extrahierte Versionen/Hashes/Modi und Mac-Ad-hoc-Signatur geprüft. [Paketnachweis](../docs/native-distribution-validation.json). Kein kalter Compiler-Reproduzierbarkeits-, DMG-, Notarisierungs- oder Windowsnachweis |
| Privater 0.5-Releaseentwurf / vorbereitet, unveröffentlicht | Sechs Assets bytegleich hochgeladen/rückgelesen, Release-ID `427556636`, Ziel Produktmerge `9f018a1`; Latest blieb `v0.3.0`. [Betriebs-/Draftnachweis](../docs/release-operations-2026-10-29-validation.json). Dies ist keine 1.0-Freigabe |
| SSH-Statuslatenz / gemessener Teilnachweis | [Draft-PR #27](https://github.com/the-fin-at/agent-pool/pull/27), Head `c6be2d9b0904685bbdfe0b11b7063ecf93bb337d`: 20 echte gecachte Statusaufrufe, p95 652,73 ms, Maximum 686,13 ms unter dem 3-s-Ziel; keine Inferenzmessung. Noch kein gemergter endgültiger Performanceabschluss |
| Native Mac-Reaktionsfähigkeit / offen | Tatsächlich gesperrte Console verhinderte den Messstart; Vorprüfung Exit 77. Nach Entsperrung nativen Blockier-Kontrolllauf und 2-s-Verzögerungslauf ausführen, Eventloop-p95 < 100 ms / Maximum < 500 ms und sichtbare Interaktion belegen, exakten Head unabhängig reviewen |
| Native Windows-Abnahme / offen, vom Nutzer zeitlich zurückgestellt | Noch kein Host; manuelle/native Installation, CLI/UI/Login/Timeout/Bestandserhalt weiter erforderlich, bevor Windows-Support als abgenommen gilt. CI-Abschaltung ersetzt diesen Nachweis nicht |
| Gehostete GitHub-CI / bewusst deaktiviert, frühere Pflicht ersetzt | Johannes ordnete ausdrücklich „Disable all ci checks in gh dann mach weiter“ an. Alle drei Workflows `disabled_manually`, keine aktiven Runs; `main` ohne erforderliche Statuschecks. [Entscheidung](entscheidungen.md), [API-Beleg](../docs/release-operations-2026-10-29-validation.json). Kein grüner CI-Pass; keine automatische Reaktivierung bei Billingänderung. Passende manuelle/native Tests und Reviews bleiben Pflicht |
| Endgültiger 1.0-Vertriebsweg / offen | Private Draftvorbereitung entscheidet nicht die endgültige Freigabe; unterstützte Plattformen, gewählten Verteilungsweg und dafür nötige Signierung/Notarisierung anhand echter Pakete festlegen und prüfen |
| Abschließende 1.0-Releaseentscheidung / offen | Nach den verbleibenden Pflichtnachweisen Scope/README/Skills/Hilfe, finale Paket-/Installationsbelege und Reviews desselben Kandidaten zusammen prüfen; keine unbewiesene Plattformunterstützung ankündigen |

Die CI-Entscheidung ersetzt ausdrücklich die frühere P0-Zeile „gehostete Releaseprüfung“ samt Billing-/Runnerbeschaffung als Voraussetzung. Der fachliche Maßstab wird weiterhin durch tatsächliche manuelle/native Ausführung mit Commit-/Artefaktbindung getragen. Alte Fehlchecks bleiben historische Fehlchecks. Die noch offenen nativen und Vertriebsgrenzen verhindern weiterhin eine behauptete vollständige 1.0-Abnahme.

Die gemeinsame Basis `9a3bda9d55a92e8f5c7904d71ed6dcd3be0afce5` bestand am 29.10.2026 um 07:21:33 UTC außerdem 15 manuelle Prüfkommandos in einer sauberen isolierten Mac-Arbeitskopie: Rust-Format/Workspace-Check/Clippy einschließlich Desktop, 85 Kern-/CLI- und zwei Bridge-Tests, Beispiel-/CLI-Build, 23 native Kompatibilitätsfälle, Frontend-Typecheck/22 Tests/Build sowie sieben Upgrade-Safety- und sieben tatsächliche Mac-Pakettests. Die Python-Discovery fand 145 Tests: 115 bestanden, 30 Tk-GUI-Tests wurden wegen fehlendem `_tkinter` übersprungen. Das ist kein heutiger 145-Pass und keine neue GUI-Abnahme. [Kommandos, Loghashes und Grenzen](../docs/release-operations-2026-10-29-validation.json) dokumentieren den manuellen Ersatznachweis bei bewusst deaktivierter CI; Windows, native UI-Performance und Realhost-Fehlerkampagne wurden dabei nicht erneut ausgeführt.
