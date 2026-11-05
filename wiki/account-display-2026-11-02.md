# Accountanzeige: Untersuchung vom 2026-11-02

Auftrag: [Issue #41](https://github.com/the-fin-at/agent-pool/issues/41), Chief-of-Staff-Chat `01a19de5-040e-76f2-b8b5-3dd5a8366034`. Ausgangsrevision: `the-fin-at/agent-pool@992a0f6443b7852cad9c0592bc313d1dd0ee0bfe`. [Auftragsregister](auftraege.md) · [Index](index.md).

## Beobachtungen und Ursachen

Am 2026-11-02 zeigte die native lokale App 0.5.2 fünf Karten bei vier verbundenen Accounts. Die bestätigten Aliase `claude-default` und `voxbot` gehörten zu demselben Konto. Am genannten Ausgangsstand deduplizierte die Oberfläche ihre Zählung, aber nicht ihre Karten. Die rote React-Reproduktion zeigte zwei Karten bei einem verbundenen Account; der spätere App-Regressionstest erwartete vier Karten und erhielt fünf. Das Backend hatte die Aliasbeziehung bereits verifiziert. Gleichlautende E-Mail-Adressen allein begründen keine Zusammenfassung.

Am 2026-11-02 meldete die native Codex-CLI 0.166.0 für das betroffene Profil im Workspace THE-FIN 100 Prozent Verbrauch im 300-Minuten-Fenster und 16 Prozent im Wochenfenster. Der allgemeine `codex`-Bucket und die Legacy-Top-Level-Antwort stimmten überein; ein Hold fehlte. Zusätzlich meldete der Anbieter ausdrücklich `rateLimitReachedType=workspace_member_credits_depleted`, `spendControlReached=false` und kein verfügbares Zusatzguthaben. Fleet verwarf am Ausgangsstand den expliziten Grund und leitete nur „Limit erreicht“ aus dem Prozentwert ab. Diese Beobachtung beweist keine Sperre anderer Accounts, Workspaces oder Abrechnungswege und rechtfertigt keine erfundenen freien Prozentwerte.

Quelle: datensparsame read-only App-Server-Probes (`account/read` mit `refreshToken=false`, `account/rateLimits/read`), lokal erzeugte CLI-Schemata `RateLimitSnapshot` und `RateLimitReachedType`, normalisierte [Nachweise](../docs/account-display-2026-11-02-validation.json). Es wurden keine Modellturns oder neuen Logins ausgeführt.

## Vereinbarter Fixvertrag am 2026-11-02

- Die normale Accountansicht gruppiert bestätigte Aliase nach Anbieter und kanonischem Profil, bevorzugt eine verbundene Standardreferenz und fällt bei fehlender/getrennter Referenz auf einen verbundenen Alias zurück. Suche berücksichtigt alle Gruppenmitglieder.
- „Alle Profile anzeigen“ erhält individuelle Kontexte, Details und Aktivierungsfunktionen. Auth-Verzeichnisse, Pins und Schedulerlogik werden nicht umgedeutet.
- Der allgemeine Codex-Bucket liefert den optionalen spezifischen Limitgrund; Accountmetadaten liefern den Workspace. Modellbezogene Gründe werden nicht als allgemeine Accountsperre übernommen. Alte Anbieterformate bleiben kompatibel.
- Die Oberfläche unterscheidet Mitglieds-/Workspace-Guthaben, Mitglieds-/Workspace-Nutzungslimits und Zeitkontingente; die Prozentwerte bleiben Anbieterbeobachtungen. Fehlgeschlagene/veraltete Abfragen werden nicht als aktueller Limitgrund präsentiert.

## Abnahme

Implementierungs-, Test-, Review- und Installationsstatus werden im [Auftragsregister](auftraege.md) und im [normalisierten Nachweis](../docs/account-display-2026-11-02-validation.json) datiert geführt. Ein lokaler Fix umfasst keine Serveraktualisierung, Windowsabnahme, Hosted-CI-Reaktivierung oder öffentliche Freigabe.

### Lokaler Abschluss am 2026-11-02

Am Quellstand `the-fin-at/agent-pool@e61edc9d5770db4ccecd89c63b2de1a78d315763` ersetzte 0.5.3 den oben beschriebenen Ausgangsfehler: 38 React- und 94 Rust-Workspace-Tests, unabhängiges Review und neun tatsächliche native Prüfungen der installierten App bestanden. Die Bestandsdaten und Auth-Kontexte blieben erhalten. Ein zusätzlicher Reviewbefund zur gleichen E-Mail in einem anderen Workspace wurde vor Abschluss korrigiert. Johannes bestätigte, dass seine Annahme über freie Kapazität ein Missverständnis war; es wurde keine positive Kapazität erfunden. [Abnahmeregister](auftraege.md) und [Nachweis](../docs/account-display-2026-11-02-validation.json) enthalten die Grenzen.
