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
