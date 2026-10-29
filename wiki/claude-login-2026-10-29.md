# Claude-Anmeldung: Diagnose und erfolgreicher Folgelauf am 2026-10-29

[Wiki-Index](index.md) · [Aufträge](auftraege.md) · [Releaseplan](release-1.0.md) · [Entscheidungen](entscheidungen.md)

## Drei getrennte Befunde

Am 29.10.2026 untersuchte der Chief of Staff auf Johannes' Auftrag eine nicht sichtbar abgeschlossene Claude-Anmeldung der installierten nativen Agent-Fleet-App 0.5.0. Bezugsstand ist `the-fin-at/agent-pool@ada7c015fbd697d6cda94b312d11a19c8d60d3dd`, geprüfter Produktcode `c47144087d3d7f665600ef0183af1c94dcd5180d`. Der [normalisierte Nachweis](../docs/claude-login-2026-10-29-validation.json) bindet die sanitisierten Quellberichte per SHA-256 und enthält keine Codes, OAuth-URLs oder Credential-Inhalte.

| Befund vom 29.10.2026 | Aussage und Grenze |
| --- | --- |
| Früherer tatsächlicher Versuch | Johannes bestätigte Codeeingabe in der App und Klick auf den Abschlussknopf. Die gespeicherte Sitzung endete später `cancelled`; frühere Providerantwort und Abbruchaufrufer sind nicht erhalten. Daraus folgt weder ein manueller Nutzerabbruch noch ein nachgewiesen ungültiger Code oder die genaue damalige Ursache. |
| Separat bestätigter Fehler [#35](https://github.com/the-fin-at/agent-pool/issues/35) | Native Claude-Code-2.1.312-Quellinspektion zeigt eine behebbar abgewiesene Eingabe ohne erneuten Prompt. Zwei isolierte kontrollierte Protokollläufe über die tatsächliche Fleet-0.5-CLI blieben danach `verifying`; erneute Eingabe wurde blockiert, obwohl der Provider weiter wartete. Die Erwartung `awaiting_code` war zweimal rot. Das wurde unabhängig validiert; es war keine echte OAuth-/GUI-Wiederholung. |
| Späterer ausdrücklich beauftragter echter Login | Offizielle Browserautorisierung, vollständiger Code über die Browser-Kopierfunktion in das maskierte native App-Feld und Abschlussklick führten bei demselben vorhandenen lokalen Profil zu `succeeded`, bestätigter nativer Subscription-Authentifizierung und sichtbarem verbundenem/aktiviertem Account. Dafür wurde kein Appfix vorgenommen. |

## Positiver Folgelauf und Nachkontrolle

Der tatsächliche positive Bericht wurde am 29.10.2026 um 15:45:18 UTC erfasst und bis 15:46:52 UTC nachgeprüft. Die beobachtete Phase `verifying` bis `succeeded` dauerte 7,072 s. Native `auth status` bestätigte `loggedIn=true`, `authMethod=claude.ai` und exakt das dem Profil zugeordnete Konfigurationsverzeichnis. Fleet meldete denselben Account im Cache und Status als verbunden und aktiviert; die reale App-Übersicht zeigte einen verbundenen Claude-Account und „Für Aufträge aktiv“. Die vorherige Default-Claude-Authentifizierung blieb beim separaten Nachcheck bestätigt.

`doctor` und lokaler Monitor mit Refresh endeten jeweils mit Exit 0. Der Monitor bestätigte einen verbundenen Claude-Account bei null bekannten Claude-Quotenfenstern; unbekannte Quoten bedeuten keinen Authentifizierungsfehler. App- und CLI-Hashes entsprechen weiter den geprüften installierten 0.5-Artefakten. Bei der Bereinigung endete der eigene Beobachter und der eigene leere Browser-Tab wurde geschlossen; ursprüngliche Safari-Tabs blieben offen. Die Zwischenablage wurde vom Beobachter weder ausgelesen noch geleert.

## Offene Grenze nach dem Erfolg

Der positive vollständige Codepfad ist damit tatsächlich nachgewiesen. Er widerlegt den reproduzierten Retry-Lockout nicht und beweist die Ursache des früheren Versuchs nicht. [Issue #35](https://github.com/the-fin-at/agent-pool/issues/35) blieb am 29.10.2026 offen: eine sicher zurückgewiesene Eingabe muss korrigierbar werden, ohne Erfolg vorzutäuschen. Die Diagnose und der erfolgreiche Login enthielten keine Implementierung, keinen kostenpflichtigen Inferenzjob, keine produktive Linux-Aktion und keine CI-Änderung.

Die bewusste CI-Abschaltung sowie die offene native Windows-Abnahme, endgültige Vertriebs-/Signierentscheidung und gesonderte 1.0-Freigabe bleiben nach dem [Releaseplan](release-1.0.md) bestehen. Die Erfolgsbeobachtung ergänzt die historischen Abnahmen; sie ersetzt keine umfassende Fehlerbehandlung oder Plattformabnahme.
