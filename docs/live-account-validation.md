# Vier echte Profile: Proxy-Aufträge und Kontingentanzeige

Am 28.10.2026 auf dem eingerichteten Linux-Pool `claw-remote` durchgeführt. Es handelt sich um echte Subscription-Inferenz über die native Provider-CLI, keine kontrollierte Provider-Test-CLI. Die Profile wurden zuvor durch den Besitzer angemeldet.

## Aufträge

Für jedes Profil wurde ein read-only Auftrag mit festem Profil, stabilem eigenem Schlüssel, maximal 180 Sekunden und einem Versuch über den öffentlichen SSH-/Queue-Proxy eingereicht. Eine neue Server-Testdatei enthielt einen zufälligen, im Prompt nicht genannten Marker sowie `[19,23,7]`. Jeder Bericht lieferte den richtigen Marker, Summe `49`, Anzahl `3` und den jeweiligen Profil-Tag. Keine Dateiänderungen durch die Agenten erlaubt.

| Profil | Job-ID | Resultat | Versuche |
| --- | --- | --- | --- |
| server-codex | c72be6e165a041a2bda7a4d234f0e7da | succeeded, Ergebnis geprüft | 1 |
| codex-2 | 9fb0b88925ed466e9c7a06daf8740b89 | succeeded, Ergebnis geprüft | 1 |
| codex-3 | 17f5ea18377e43f7927e209664e24d9d | succeeded, Ergebnis geprüft | 1 |
| server-claude | b4fb4c8e7a114d4c9109b3c1ba2f5d61 | succeeded, Ergebnis geprüft | 1 |

Nach der Parser-Korrektur erneut über den Proxy: Claude-Job `17c757bb747244208050d33dac5b8c6e`, ebenfalls korrekt und ein Versuch. Die nativen Referenzmessungen erzeugten zusätzlich zwei kurze Claude-`OK`-Antworten zur unabhängigen Erfassung der Usage-Ereignisse; diese zusätzlichen Diagnosen sind keine Proxy-Jobs.

## Gefundener und korrigierter Fehler

Claude Code 2.1.312 lieferte Prozentwerte innerhalb `rate_limit_info.unifiedWindows`. Der alte Parser las nur das äußere limitierende Fenster. Dadurch fehlten Wochenlimit und Prozentsätze in der App. Der sanitisiert gespeicherte reale Event erzeugte zuerst einen roten Regressionstest: erwartet 0 % Verbrauch/5 Stunden und 2 %/Woche, erhalten nur unbekannten 5-Stunden-Verbrauch.

Version 0.4.2 liest beide nativen Fenster, ihre Resets und gegebenenfalls Modellfenster. Eigenständige Statuswerte überschreiben das äußere Fenster; Overage-Metadaten werden nicht als ausgeschöpftes Abo interpretiert. Legacy-Ereignisse bleiben unterstützt. Das Review fand zusätzlich einen gemischten Reset-Alias-Fall (`resetsAt`/`resets_at`), ebenfalls erst rot reproduziert und dann behoben.

## Vergleich native CLI → Server-Cache → echte Tk-Widgets

Codex-Referenz: dokumentierte `account/rateLimits/read`-Antwort je nativem Profil. Claude-Referenz: reale native `rate_limit_event`-Ereignisse. Keine Credential-Dateien, keine privaten Usage-HTTP-Endpunkte gelesen. Ein serverseitiger Metadatenlauf speicherte dieselben Beobachtungen für einen zeitlich eindeutigen Vergleich.

Im echten nativen Dashboard wurden reale Remote-Daten geladen. Gegen die unabhängigen Rohdaten geprüft: Verbrauch zu freiem Anteil, Dauer, Reset-Timestamp, absolute Reset-Beschriftung, Zahlen auf den Canvas-Kreisen, Wochen-Text und geometrische Balkenlänge. Kein Mock des Transports oder der Quoten. Nur Identitäten wurden für die Screenshots ausgeblendet.

| Profil | Frei im 5-Stunden-Fenster | Frei im Wochenfenster |
| --- | --- | --- |
| codex-2 | 99 % | 100 % |
| codex-3 | 99 % | 100 % |
| server-codex | unbekannt, Anbieter meldet keines | 74 % |
| server-claude | 100 % | 98 % |

Das sind die nativen Beobachtungen zum Aufnahmezeitpunkt; andere laufende Nutzung kann die Werte anschließend verändern. Beim ursprünglichen Codex-Profil ist dessen primärer Slot tatsächlich 10080 Minuten lang. Die App zeigt ihn deshalb als Woche und erfindet kein 5-Stunden-Limit.

[Screenshot Codex](../design/2026-10-28/live-accounts/limits-codex.png) · [Screenshot Claude](../design/2026-10-28/live-accounts/limits-claude.png) · [maschinenlesbare Nachweise](live-account-validation.json).

## Abnahme und Installation

134 Tests auf Mac mit echtem Tk bestanden. Auf echtem Linux: 134 Tests bestanden, davon 30 GUI-Tests mangels Display übersprungen. Die reale Mac-Oberfläche ist separat nachgewiesen. Standards-Review: 0 offene Befunde. Spec-Review: 0 offene Befunde.

Client und Server auf 0.4.2 aktualisiert. Native Mac-App gebaut, Ad-hoc-Signatur geprüft, Remote-Smoke mit vier verbundenen Accounts und zwei Claude-Fenstern bestanden. Das CLI-Archiv stimmt byteweise mit den Python-Quellen überein. Vor dem kontrollierten Neustart des eigenen Workers waren keine Jobs mehr offen. Authentifizierungen und fremde Dienste wurden erhalten.

GitHub-CI und native Windows-Abnahme bleiben separate Nachweise; die bekannte Abrechnungssperre ist kein grüner CI-Lauf.
