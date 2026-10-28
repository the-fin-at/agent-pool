# UI-Texte für Agent Fleet

Überarbeitet mit dem unslop-Skill am 28. Oktober 2026. Die Begriffe bleiben getrennt: Account ist die Anmeldung beim Anbieter, Profil ist die lokale Konfiguration für Aufträge und Kontingent ist der verfügbare Anteil eines gemeldeten Limits.

## Bereits im Desktop-Code geändert

| Bisher | Neue Fassung |
|---|---|
| Nutzung & Limits | Kontingente |
| Alle verbundenen Accounts. Die gemeldeten Kontingente auf einen Blick. | Verbleibendes Kontingent pro Account. |
| Jetzt aktualisieren | Aktualisieren |
| Automatisch · 60 s | Alle 60 Sekunden aktualisieren |
| Quotenfenster gemeldet | Gemeldete Limits |
| Auch unverbundene Profile | Alle Profile anzeigen |
| Quote unbekannt | Kontingent unbekannt |
| Stand prüfen | Daten nicht aktuell |
| Noch keine Quotenabfrage | Noch keine Kontingentdaten |
| CLI-Hauptaccount · nur Anzeige | Codex-CLI, nur Anzeige |
| Profil pausiert | Für Aufträge deaktiviert |
| Noch keine Quotenbeobachtung aus der Claude-CLI vorhanden. | Noch keine Kontingentdaten aus der Claude-CLI. |
| Profil(e) prüfen | 1 Abfrage fehlgeschlagen / mehrere Abfragen fehlgeschlagen |
| Reset erreicht · Aktualisierung nötig | Reset-Zeit erreicht. Bitte aktualisieren. |

Wenn eine Suche keine Treffer liefert, fordert die Ansicht zum Ändern der Suche auf. Sie zeigt dort keine unpassende Login-Anweisung. Wenn noch keine Werte gespeichert sind, behauptet die Fehleranzeige keinen früheren erfolgreichen Abruf.

Ein globaler Abfragefehler bleibt bis zur nächsten erfolgreichen Abfrage sichtbar. Der Aktualisierungstimer überschreibt ihn nicht mehr mit dem Zeitpunkt einer älteren erfolgreichen Abfrage.

## Texte für den gewählten Entwurf

Diese Texte ersetzen beim Nachbau die Beschriftungen des Bild-Mockups. Sie setzen keinen weiteren Menüpunkt und keine zusätzliche Datenquelle voraus.

| Stelle | Text |
|---|---|
| Navigation und Seitentitel | Alle Accounts / Codex / Claude |
| Ringwert | 72 % |
| Beschriftung im Ring | frei im 5-Stunden-Fenster |
| Wochenwert | Wochenkontingent, 41 % frei |
| Niedriges Restkontingent | Wenig frei |
| Fehlender Prozentwert | Kein Wert gemeldet |
| Datenstand | Stand 14:02 |
| Nächste automatische Abfrage | Nächste Abfrage in 42 s |
| Zusätzliche Anzeigequelle | Nur Anzeige |
| Erläuterung der Anzeigequelle | Codex-Standardanmeldung. Dieses Konto erhält keine Aufträge über Agent Fleet. |
| Ausführungsprofil | Für Aufträge aktiviert / Für Aufträge deaktiviert |
| Claude-Hinweis | Werte aus dem letzten Claude-Lauf. |

Prozentwerte zeigen einen Anteil des Kontingents. Das Fünf-Stunden-Fenster ist keine verbleibende Rechenzeit. Fehlende Daten werden nicht als 0 % angezeigt. Nach einer abgelaufenen Reset-Zeit zeigt die App erst wieder einen aktuellen Wert, wenn der Anbieter neue Daten gemeldet hat.

## Opus-Einschätzung

[Unveränderte Antwort von Claude Opus 5.5](claude-opus-5-5-design-review.md).

Der Aufruf über die bereits angemeldete normale Claude-CLI wurde erfolgreich abgeschlossen. Das tatsächlich gemeldete Modell war `claude-opus-5-5`. Es hat den Anthropic-Skill `frontend-design:frontend-design` aufgerufen und den Mockup, den vorhandenen Code, die THE-FIN-Markenregeln und unslop gelesen.

Die Gestaltungsempfehlung behält Seitenleiste, Kreis-Anzeigen und THE-FIN-Palette bei. Sie ergänzt klare Rollen und Datenstände, reduziert doppelte Statusangaben und sieht drei, zwei oder eine Spalte je nach Fensterbreite vor. Ein Wechsel des Desktop-Frameworks wird erst nach einer Prüfung von Kreisen und Schrift auf beiden Plattformen empfohlen.

Nicht ungeprüft übernommen werden eine pauschale neue Frist für Claude-Daten und eine leere Kreis-Anzeige allein wegen eines anderen erschöpften Modell- oder Wochenlimits. Beides muss je Datenquelle bzw. betroffenem Fenster entschieden werden.

Die unveränderte Opus-Antwort entstand vor der Umbenennung. Der Produktname für die Umsetzung lautet Agent Fleet.
