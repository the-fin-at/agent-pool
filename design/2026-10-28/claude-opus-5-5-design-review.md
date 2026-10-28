**Modell:** Claude Opus 5.5 (`claude-opus-5-5`).
**Skills:** `frontend-design` (aufgerufen, SKILL.md gelesen), dazu gelesen: THE-FIN `brand-guide.md`, `tokens.json` und `unslop` SKILL.md. Die generischen Vorlieben von frontend-design (auffällige Schriften, Verläufe, Texturen) habe ich bewusst nicht angewendet, weil die Markenvorgaben Vorrang haben. Übernommen habe ich die Methode: eine klare Richtung, präzise Abstände, nichts Beliebiges.
**Gelesen:** Mockup-Bild (angesehen), `agent_pool/desktop.py`, `agent_pool/monitor.py`, zusätzlich `availability()` in `agent_pool/quota.py` und das `signet.svg` aus dem Markenpaket. `tests/test_desktop.py` habe ich nicht gelesen. Alle Quellen ließen sich öffnen.

---

## 1. Gestaltungsentscheidung und drei Korrekturen

**Entscheidung:** Ich behalte den Entwurf in seiner Ruhe: Papierfläche, keine Kartenkästen, große Ringe, Terrakotta nur auf dem Bogen und der einen Aktion. Gegliedert wird über Typografie und Abstand. Neu hinzu kommt nur eine Information: Jeder Ring sagt genau, welches Fenster er zeigt, wie alt der Wert ist und ob das Profil Aufträge bekommt.

**Korrektur 1: "5 Stunden frei" ist inhaltlich falsch.** Der Text liest sich wie "noch 5 Stunden Rechenzeit". Gemeint ist der freie Anteil des Fünf-Stunden-Fensters. Darunter gehört daher "frei im 5‑Std.‑Fenster". Die Zahl wird nach deutscher Schreibweise "72 %" gesetzt, mit schmalem geschütztem Leerzeichen (U+202F).

**Korrektur 2: Rolle und Stand fehlen auf jeder Karte.** Der Personen-Avatar trägt keine Information. An seine Stelle kommen eine Anbieter-Zeile ("CODEX" / "CLAUDE"), die Rolle ("Für Aufträge aktiv", "Pausiert", "Nur Anzeige") und unten "Stand 14:02". Erst damit bleibt die Unterscheidung zwischen Account und Profil sichtbar, und ein alter Wert sieht nicht frisch aus.

**Korrektur 3: Der Kopfbereich mit Werbetitel und dreifacher Aktualisierungsanzeige.** "Alles im Blick.", "Vor 60 Sek.", der Schalter unten links und die Fußzeile "Automatisch alle 60 s" sagen alle ungefähr dasselbe. Der Titel heißt künftig wie der gewählte Navigationspunkt. Den Takt der Abfragen zeigt eine einzige Statuszeile. Die Fußzeile mit Datum und Zeitzone entfällt. Außerdem: Der Button im Mockup wirkt wie `brand` #BD775F mit weißer Schrift, das ergibt rund 3,5:1 und ist zu wenig für Text. Er braucht `accent` #9D5035 mit `accentContrast` #FEFDFB.

---

## 2. Maße und Hierarchie

Werte in px, Farben nach Rollen aus `corporate.light`. In Tk werden Schriftgrößen negativ angegeben (Pixel), damit Mac und Windows gleich groß rendern.

**Fenster:** Standard 1240 × 820, Minimum 640 × 560 (heute 760 × 560).

**Seitenleiste (Fenster ≥ 880 px):**
- 216 px breit, Fläche `surface` #F4EFE9, rechts 1 px `border`, Innenabstand 24.
- Signet 32 px, daneben "Agent Pool" in 17 px, Gewicht 500. Danach 32 px Abstand zur Navigation.
- Navigationspunkte 44 px hoch, Radius 12, Icon 20 px. Rechts steht die Anzahl in 12 px mit tabellarischen Ziffern, gedeckt (`textMuted`).
- Aktiver Punkt: Fläche `accentSoft` #FCE6DC, Text `accentText` #9D5035, Gewicht 500. Inaktive Punkte: `textSecondary`, Gewicht 400.
- Unten: der Schalter "Alle 60 s abfragen" und darunter in 12 px "Nächste Abfrage in 42 s".

**Unter 880 px:** Die Seitenleiste fällt weg. Unter dem Titel erscheint eine Pillenreihe mit "Alle Accounts · Codex · Claude", das Signet kommt mit 24 px in den Kopf. Eine reine Icon-Leiste nehme ich nicht. Bei nur drei Einträgen kosten die Beschriftungen kaum Platz, ohne sie wird die Navigation unklar.

**Kopf:**
- Seitenrand 40 px, bei schmalem Fenster 24 px.
- Titel H1 in 30 px Albert Sans Light (300), `textPrimary`. Darunter 8 px Abstand und die Unterzeile in 15 px `textSecondary`.
- Rechts: Suchfeld 240 × 36 mit 1 px `borderStrong` (Eingabefelder brauchen eine kontraststarke Kontur), daneben der Button.
- 32 px Abstand bis zum Raster.

**Raster:**
- Spaltenzahl = `min(3, floor((Inhaltsbreite + 32) / 328))`. Das entspricht einer Mindestbreite der Karte von 296 px und 32 px Spaltenabstand. Eine Karte wird höchstens 400 px breit.
- Drei Spalten gibt es also erst ab rund 1230 px Fensterbreite, das Standardfenster mit 1100 px zeigt zwei. So wird nichts zusammengedrückt.
- Zwischen den Reihen liegt eine 1 px `border`-Linie mit je 32 px Abstand. Die senkrechten Trennlinien aus dem Mockup entfallen, weil sie bei Umbrüchen in eine neue Reihe falsch stehen.

**Karte, senkrechte Anordnung (ab 2 Spalten):**

| Element | Maß |
|---|---|
| Anbieter-Zeile | 11 px, 500, Versalien, `textMuted` |
| E-Mail bzw. Kontoname | 17 px, 500 |
| Profilzeile | 13 px `textSecondary`, z. B. "Profil arbeit" oder "Codex-Standardanmeldung" |
| Pillen (Tarif, Rolle, Zustand) | 24 px hoch, 12 px, 500 |
| Ring | Ø 168, Strich 12 (bei Karten unter 340 px: Ø 144, Strich 10). Spur `border` #DCD6D1, Bogen `brand` #BD775F (3,2:1 gegen Papier, reicht für Grafik). Runde Enden. |
| Zahl im Ring | 40 px Light, tabellarische Ziffern, `textPrimary` |
| Beschriftung im Ring | 13 px `textMuted`, "frei im 5‑Std.‑Fenster", darf zweizeilig sein |
| Reset unter dem Ring | 12 px Abstand, 13 px `textSecondary` |
| Wochenzeile | 24 px Abstand, Linie, dann Label 13 px/500, Wert rechts. Balken 6 px hoch als Pille, Reset in 12 px muted |
| Fuß | "Stand 14:02" in 12 px und "Details" als Textbutton |

**Eine Spalte (Inhaltsbreite unter 624 px):** Die Karte wird waagrecht angeordnet. Links steht der Ring mit Ø 128 und einer 32-px-Zahl, rechts in einer Spalte Name, Rolle, Reset und Woche. Eine Karte ist dann etwa 176 px hoch, und das Fenster muss nicht endlos scrollen.

---

## 3. Zustände

Grundregel: Der Ring zeigt nur dann eine Zahl, wenn ein gültiger und nicht abgelaufener Wert existiert. In jedem anderen Fall steht "–", niemals "0 %". Farbe ist nie das einzige Signal, es gibt immer ein Wort dazu.

| Zustand (aus `monitor.py`) | Ring | Text |
|---|---|---|
| Frisch, ausreichend | Bogen `brand`, Zahl `textPrimary` | "Reset in 2 Std. 20 Min." |
| Wenig frei (≤ 25 % frei, entspricht der heutigen Schwelle used ≥ 75) | Bogen `warning` #986106 | Pille "Wenig frei" mit Icon |
| Limit erreicht (`availability().ready == False` oder `hold_reason`) | Leere Spur, Zahl "0 %" nur bei gemeldetem used = 100 | Pille `danger` "Limit erreicht". Dazu "Laut Anbieter wieder ab 14:20" bzw. "Pausiert bis 14:20" |
| Kein Fenster gemeldet | Spur gestrichelt in `borderStrong`, Mitte "–" | Codex: "Codex hat für dieses Fenster keinen Wert gemeldet." Claude: "Noch kein Wert aus einem Claude-Lauf gespeichert." |
| Reset vorbei (`expired`) | wie oben: "–", gestrichelte Spur | "Reset war 14:20. Neuer Wert nach der nächsten Abfrage." Bei Claude: "… nach dem nächsten Claude-Lauf." |
| Veraltet (Alter über der Schwelle) | Letzter Wert bleibt sichtbar, Bogen `textMuted`, Zahl `textSecondary` | Pille "Veraltet". Fuß in `warning`: "Stand 13:48, vor 14 Min." |
| Abfrage fehlgeschlagen (`error`) | wie veraltet | Pille "Abfrage fehlgeschlagen". "Abfrage um 14:05 fehlgeschlagen. Angezeigt: Stand 13:58." Unter "Details" steht der Fehlertext |
| Nicht angemeldet | Kein Ring, nur die Spur | "Nicht angemeldet. Anmelden mit `agent-pool login <profil>`" in Geist Mono. Standardmäßig ausgeblendet |

**Drei Folgen aus dem Code, die die Gestaltung lösen muss:**

1. **Woche und Modell-Buckets.** `availability()` prüft konservativ alle Fenster, auch Modell-Buckets. Eine Karte kann daher "Limit erreicht" melden, während der Ring 72 % zeigt. Die Pille nennt deshalb die Ursache, etwa "Wochenlimit erreicht" oder "Limit Modell X erreicht". Das betroffene Fenster erscheint als zusätzliche Balkenzeile unter "Woche". Ich zeige höchstens zwei solche Zeilen, der Rest steht in "Details". Ein anderes Fenster rückt nie unbeschriftet in den Ring.
2. **Claude ist praktisch immer veraltet.** `account_view` setzt `stale`, sobald `observed_at` älter als 150 s ist. Claude-Werte kommen aber nur aus CLI-Läufen und sind fast immer älter. Ich würde die Frische je Anbieter festlegen. Codex wird ab 150 s gewarnt. Claude zeigt das Alter immer neutral ("Stand aus Claude-Lauf, 09:14") und gilt erst ab einer Schwelle als veraltet, etwa 30 Minuten. Diese Schwelle musst du festlegen. Abgelaufene Fenster werden ohnehin nicht mehr als Wert gezeigt.
3. **Abfragefehler verschwinden sofort.** In `desktop.py` schreibt `_poll` bei einem Fehler "Aktualisierung fehlgeschlagen …" in die Statuszeile. `_clock` überschreibt das schon eine Sekunde später mit "Aktualisiert HH:MM:SS". Das verletzt deine Vorgabe direkt. Der Fehler muss in der Statuszeile stehen bleiben, bis eine Abfrage gelingt: "Abfrage um 14:05 fehlgeschlagen. Alle Werte vom Stand 13:58."

---

## 4. Texte

Begriffe, die getrennt bleiben: **Account** ist die Anmeldung beim Anbieter (E-Mail). **Profil** ist das lokale Ausführungsprofil von agent-pool. **Kontingent** ist ein gemeldetes Fenster. "Quote" und "Quotenfenster" verschwinden aus der Oberfläche.

| Bisher | Neu |
|---|---|
| "Alles im Blick." | Titel = Navigationspunkt: "Alle Accounts", "Codex" oder "Claude" |
| "3 Accounts verbunden" | "3 Accounts angemeldet · 2 Profile nehmen Aufträge an" |
| "Alle verbundenen Accounts. Die gemeldeten Kontingente auf einen Blick." | "Freier Anteil der Kontingente, wie Codex und Claude ihn melden. Aufträge startest du mit `agent-pool` in der Kommandozeile." |
| Unterzeile der Claude-Ansicht (neu) | "Werte aus dem letzten Claude-Lauf je Profil. Diese App fragt Claude nicht direkt ab." |
| "Quotenfenster gemeldet" (Kachel) | Streichen. Eine Zahl wie "5 Fenster" hilft niemandem bei einer Entscheidung. |
| "Profile für Aufträge aktiv" | "Profile nehmen Aufträge an" |
| "Quote unbekannt" | Ring "–", darunter "Kein Wert gemeldet" |
| "Stand prüfen" | Nach Ursache aufgeteilt: "Veraltet", "Abfrage fehlgeschlagen" oder "Reset vorbei" |
| "CLI-Hauptaccount · nur Anzeige" | Pille "Nur Anzeige", Profilzeile "Codex-Standardanmeldung, kein Pool-Profil, bekommt keine Aufträge" |
| "Profil(e) prüfen" | "Abfrage fehlgeschlagen bei arbeit, team". Namen statt Zähler, weil die Standardanmeldung kein Profil ist |
| "5 Stunden frei" | "frei im 5‑Std.‑Fenster" |
| "Woche frei · 41%" | "Wochenkontingent · 41 % frei" |
| "Reset am Mo., 2. Nov." | "Reset Mo., 2. Nov., 09:00" |
| "Niedrig" | "Wenig frei" |
| "Vor 60 Sek." | "Stand 14:02" und "Nächste Abfrage in 42 s" |
| "Jetzt aktualisieren" / "Aktualisieren" | "Aktualisieren". Tooltip: "Fragt Codex-Accounts ab. Claude-Werte kommen aus Claude-Läufen." |
| "Reset erreicht · Aktualisierung nötig" | "Reset war 14:20. Neuer Wert nach der nächsten Abfrage." |
| "Aktualisierung fehlgeschlagen. Letzter bekannter Stand." | "Abfrage um 14:05 fehlgeschlagen. Angezeigt: Stand 13:58." |
| "Noch keine Quotenbeobachtung aus der Claude-CLI vorhanden." | "Noch kein Wert aus einem Claude-Lauf gespeichert." |
| "Der Anbieter hat noch keine Kontingente gemeldet." | "Codex hat kein Kontingent gemeldet." |
| "Verbunden" (Status-Pille) | Entfällt. Die Rolle steht als Pille, der Normalfall braucht keine eigene Pille. |
| "Auch unverbundene Profile" | "Nicht angemeldete Profile zeigen" |
| "Accounts durchsuchen …" | "Name, E-Mail oder Tarif" (genau die Felder, die die Suche filtert) |
| "Kontingente bleiben pro Account getrennt." | Streichen, der Satz gibt keine verwertbare Information. |
| "Beispieldaten" | Nur im Mockup, nie in der App |

---

## 5. Umsetzung im bestehenden Tk-Desktop

**Bei Tk bleiben, die Logik in `agent_pool/monitor.py` schärfen.**

1. **Zustandsmodell in `monitor.py`, Texte nicht im Widget-Code.** `account_view` liefert künftig:
   - `primary`: das 5‑Std.‑Fenster des Haupt-Buckets oder `None`
   - `secondary`: Woche und Modell-Buckets
   - je Fenster einen `state` aus `ok | low | exhausted | unknown | expired`
   - je Account eine `freshness` aus `fresh | aged | failed`, mit anbieterabhängiger Schwelle
   - die fertigen deutschen Texte aus Tabelle 4

   Schwellen und Texte liegen damit an einer Stelle, Mac und Windows teilen sie, und `tests/test_monitor.py` kann alles ohne Tk prüfen. Die heutigen Balkenfarben-Schwellen (75/95) aus `desktop.py` ziehen mit um.
2. **`desktop.py` neu gliedern** in `Sidebar`, `Header`, `QuotaRing` (eine Canvas-Klasse mit `draw(state, value)`) und `AccountCard`. Die Farben kommen als Konstanten aus `corporate.light`. Die Skill-Datei wird zur Laufzeit nicht gelesen.
   - Den Spaltenwechsel in `_resized` erweitern auf 1/2/3 Spalten plus waagrechte Karte.
   - Karten nicht mehr bei jeder Abfrage zerstören und neu bauen, wie `render()` es heute tut, sondern pro Account-Namen aktualisieren. Sonst flackern die Ringe.
   - Die Navigation filtert nach `provider`. Tastenkürzel Cmd/Strg+1/2/3.
   - Die Konstruktorparameter `initial`, `refresh_fn` und `start_refresh` beibehalten. Vermutlich testet `tests/test_desktop.py` darüber, gelesen habe ich die Datei nicht.
3. **Signet ohne SVG-Unterstützung.** Tk kann kein SVG laden. Die Geometrie des Originals ist aber einfach: zwei Kreisbögen mit Radius 25,4 um (50, 50), vier Punkte mit r = 3,1 und ein Nadel-Polygon. Das lässt sich mit unveränderten Koordinaten auf eine Canvas skaliert zeichnen. Tk-Bögen haben keine runden Enden, deshalb kommen an die Enden kleine Kreise (r = 2,3). Dasselbe gilt für die Ring-Enden.
4. **Schrift.** Albert Sans liegt im Markenpaket als TTF vor (Light, Regular, Medium, SemiBold) und muss vor `tk.Tk()` für den Prozess registriert werden. Unter Windows geht das mit `AddFontResourceExW(…, FR_PRIVATE)` über ctypes, auf dem Mac mit `CTFontManagerRegisterFontsForURL` oder `ATSApplicationFontsPath` im App-Bundle. Tk kennt nur die Gewichte normal und bold, Light muss also als eigene Familie angesprochen werden. Ob "Albert Sans Light" auf beiden Systemen so aufgelöst wird, ist das größte technische Risiko. Ein falscher Fall auf Bold wäre ein sichtbarer Bruch. Als Ersatz dienen Helvetica Neue bzw. Segoe UI.

**Wann ein Wechsel begründet wäre:** Der Tk-Canvas glättet unter Windows keine Kanten (GDI). Ein 12 px breiter Ring wirkt dort treppig, auf dem Mac nicht. Wenn der Test unten das bestätigt und Pillow-Supersampling (Ring dreifach rendern und verkleinern, eine zusätzliche Abhängigkeit) nicht reicht, wäre PySide6 der belegbare Wechsel:
- `QPainter` glättet Kanten.
- `QFontDatabase.addApplicationFont` lädt die Schrift mit echten Gewichten.
- QtSvg rendert das Signet direkt.
- Die Darstellung auf HiDPI-Bildschirmen funktioniert ohne Zusatzarbeit.

Der Aufwand: `desktop.py` mit gut 340 Zeilen wird neu geschrieben. `monitor.py`, `quota.py` und die CLI bleiben unverändert, weil das Lesemodell keine UI kennt. Dazu kommen ein deutlich größeres Paket und LGPL-Pflichten bei der Verteilung. Ohne das Ergebnis des Tests empfehle ich den Wechsel nicht. Eine Webtechnik bringt hier keinen Vorteil, der den Umbau rechtfertigt.

---

**Nächster Schritt:** Zuerst das Zustandsmodell aus Abschnitt 5, Punkt 1 in `agent_pool/monitor.py` mit Tests in `tests/test_monitor.py` umsetzen. Dazu gehören die anbieterabhängige Frische, das Ende des sofortigen Überschreibens von Fehlern in der Statuszeile und die Texte aus Tabelle 4. Das ist unabhängig vom UI-Toolkit, behebt zwei echte Fehler und legt fest, was jeder Ring zeigen darf. Direkt danach folgt ein kurzer Test unter Windows und macOS mit einem einzelnen `QuotaRing` und Albert Sans Light in Tk. Er entscheidet, ob Tk reicht.