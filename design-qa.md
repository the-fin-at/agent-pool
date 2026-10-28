# Agent Fleet · Native Desktop Design QA

final result: passed

## Vergleich und Nachweise

- Visuelle Quelle: `design/2026-10-28/agent-fleet-the-fin-sidebar.png`, 1568 × 1003 px.
- Implementierung: `design/2026-10-28/implementation-final.png`, echte native macOS-Fensteraufnahme, 3136 × 1968 px bei 2× Pixeldichte.
- Normalisierung: auf 1568 × 984 px verkleinert, 28 px native Titelleiste entfernt. Inhalt: 1568 × 956 px, gespeichert als `implementation-final-content.png`. macOS begrenzt die Fensterhöhe auf dem Prüfbildschirm auf 956 px. Die Quelle wird für den Vergleich unten auf dieselben 956 px beschnitten, ohne Strecken des Inhalts.
- Gemeinsamer Vergleich: `design/2026-10-28/comparison-final.png`; lesbarer Account-/Kreis-/Wochenbereich in `comparison-final-detail.png`. Beide Bilder wurden gemeinsam geöffnet und visuell verglichen.
- Zustand: heller THE-FIN-Stil, Alle Accounts, dieselben drei Beispielaccounts Privat/Arbeit/Team; 72/92/18 % im 5-Stunden-Fenster und 41/86/12 % im Wochenfenster. Reset-Anzeigen laufen in der App relativ zur realen Aufnahmezeit und stimmen deshalb nicht sekundenweise mit dem statischen Mockup überein.
- Zusätzliche echte Fensteraufnahme: `implementation-narrow.png`, 760 × 700 logische Pixel; Navigation oberhalb des Inhalts, Accountdaten neben einem 168-px-Kreis. Claude-Filter und leerer Zustand wurden zusätzlich im echten Tk-Test geprüft. Eine zusätzliche leere Screenshot-Ansicht konnte nicht gespeichert werden; die breite Quell-/Implementierungsaufnahme und die schmale Aufnahme liegen vollständig vor.

## Vergleichsverlauf

1. Erste Aufnahme: zu kleine Typografie und System-Fallback Helvetica Neue statt Albert Sans (P1). Korrigiert durch prozesslokale Fontregistrierung vor Tk-Initialisierung, eingebettete aufrechte TTFs und eine auf großen Fenstern mitwachsende Schriftgröße. Nachweis: finale Aufnahme und nativer Smoke-Bericht melden Albert Sans.
2. Frühe breite Ansicht: Details-Schaltflächen am unteren Rand teilweise abgeschnitten (P2). Unteren Toolbar-Abstand und Kartendichte angepasst. Finale Geometrie: Kartenbeginn y=274, sichtbare Inhaltsfläche 617 px, Kartenhöhe 616 px; die Schaltflächen sind vollständig sichtbar.
3. Frühe schmale Ansicht: großer vertikaler Kreis verdrängt wesentliche Daten unter den sichtbaren Bereich (P2). Unter 880 px horizontale Zusammenfassung mit kleinem Kreis, darüber eine beschriftete Navigation samt Server- und Auftragssteuerung. Kein horizontal abgeschnittener persistenter Aktionsbereich.
4. Avatar-/Identitätsbereich: Größe und Anordnung näher an die Referenz gebracht. Plan, Rolle und Warnzustand liegen bei der Identität. Lange E-Mail-Adressen werden für die verfügbare Breite gekürzt; Details zeigen die volle Adresse.
5. Letzter Vergleich: keine offenen P0/P1/P2-Befunde.

## Fünf Prüfflächen

- Typografie: Albert Sans aus dem Paket, aufrecht, normale Überschriften und klare Hervorhebungen. Zahlen und Beschriftungen lesbar und ohne Überlagerung. Header- und Eingabeschriften reagieren auf die Fenstergröße.
- Abstände/Layout: warme Seitenleiste, drei Kontingentspalten mit feinen Trennlinien; zwei und eine Spalte bei geringerer Breite. Aufträge, Serverauswahl und Such-/Profilfilter sind notwendige Ergänzungen zur produktiven App.
- Farben: originale corporate.light-Rollen, Papier #F9F6F2, Fläche #F4EFE9, Text #1B1612, Muted #6D6863, Marke #BD775F und Aktionsfarbe #9D5035. Warnungen erhalten Text und Zustandsfarbe. Keine Aussage hängt allein von Farbe ab.
- Assets: originales THE-FIN-Kompass-Signet und daraus abgeleitetes App-Icon, Geometrie unverändert. Bibliotheksicons aus Bootstrap Icons v1.11.3 mit MIT-Lizenz; keine nachgezeichneten Markenlogos. Kreis- und Balkendarstellungen sind echte datenabhängige Charts.
- Texte/Inhalt: Agent Fleet, Alle Accounts/Codex/Claude, frei im 5-Stunden-Fenster, Wochenkontingent, Wenig frei. Fehlende Werte erscheinen als unbekannt, abgelaufene Werte nicht als 0 oder 100 %. Ausführungsrolle, Datenstand und Fehler bleiben erkennbar.

## Funktionale Abnahme

93 Tests mit echtem Tk, einschließlich Anbieter-Navigation über die Schaltfläche, kombinierter Suche, Verbindungsauswahl, weiterhin bedienbarer Wiederholung nach ungültigem Serverwechsel, verworfener alter Serverantworten, Ablauf eines Kontingents ohne automatische Abfrage, getrenntem Wochen- und 5-Stunden-Limit, Timer-Aufräumen und responsiven Aktionsbereichen. Remote- und Manager-Tests sind Teil desselben Laufs. Native macOS-App: 1280 × 840, Albert Sans, drei verbundene Accounts, erfolgreiche Abfragen ohne Fehler. Der separate Linux-/OpenSSH-Nachweis liegt in `docs/remote-ssh-validation.json`.

## Erwartete Plattformunterschiede und P3

Native Checkboxen, Eingabefelder und Scrollleisten folgen Tk und ersetzen die illustrative Toggle-Darstellung. Exakte Generierungsfarben werden durch die offiziellen THE-FIN-Tokens ersetzt. Statische Beispieltermine werden durch tatsächliche Reset-Zeitpunkte ersetzt. Die Windows-Portabeldatei enthält dieselben Assets; ein echter Windows-GUI-/EXE-Lauf bleibt unbestätigt. Der Windows-CI-Runner startet wegen der dokumentierten GitHub-Abrechnungsblockade nicht. Dies ist keine Behauptung plattformübergreifender visueller Abnahme.
