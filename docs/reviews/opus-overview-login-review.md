# Opus 5.5 – Overview und Login

Zwischenstand: angefordertes und bestätigtes Modell `claude-opus-5-5`, native CLI ohne Tools.

# Gutachten: Native Login-Sessions / Übersicht

Grundlage ist nur der gezeigte Code. `cli.py`, `store.py` und `providers.py` kenne ich nicht. Wo das Ergebnis von deren Semantik abhängt, steht das dabei.

## Kritisch

**1. Poll-Ketten vervielfachen sich (GUI)**
`handle_panel_event` plant nach *jedem* `login`-Event mit aktivem Zustand ein neues `poll_login` ein, auch im Zweig „unverändert“. `submit_login_code` und `cancel_login` erzeugen eigene Events, die laufende Kette bleibt aber bestehen. Nach jeder Nutzeraktion läuft also eine Kette mehr.
- Repro: Claude-Login starten, Code senden. Danach laufen zwei parallele SSH-Polls im Abstand von 1,2 s.
- Fehler-Events planen ebenfalls nach.
- Abhilfe: genau eine Poll-Kette pro `login_key`, z. B. über einen gespeicherten after-Handle oder einen Sequenzzähler.

**2. Sackgasse bei falschem oder nicht angenommenem Claude-Code**
- Nach `input` setzt der Worker `verifying`.
- `observe` entfernt in diesem Zustand `state` und `message`.
- `provide_code` akzeptiert nur `awaiting_*`, und die GUI zeigt kein Eingabefeld mehr.

Fragt die CLI nach einem falschen Code erneut oder hängt sie, bleibt die Session bis zu 15 Minuten in `verifying`. Das Profil ist so lange deaktiviert, und ein neuer Start meldet „läuft bereits“. Abbrechen ist möglich, ein erneuter Versuch innerhalb derselben Session nicht.

**3. Verwaiste Sessions bei GUI-Wechsel**
Folgende Aktionen beenden die laufende Session nicht:
- `go_back`
- `select_scope` / `_select_target`
- Fenster schließen (`close`)
- erneutes `show_login`

Der Worker läuft weiter, das Profil bleibt deaktiviert, und `show_login` erzeugt einen neuen Key. Die alte Session lässt sich nicht wieder aufnehmen.
- Repro: Login starten, „Zurück“, dann „Account hinzufügen“ mit demselben Namen. Ergebnis: „Anmeldung für dieses Profil läuft bereits“ bis zum Ablauf der TTL.
- Abhilfe: beim Verlassen abbrechen, oder aktive Sessions pro Profil über `auth get` beziehungsweise eine Liste wieder anbieten.

**4. Profil bleibt nach Absturz des Workers dauerhaft deaktiviert**
`enabled=False` wird vor dem Login gesetzt und erst im `finally` zurückgesetzt. Bei SIGKILL, OOM oder einem Neustart des Servers läuft `finally` nicht.
- `status()` markiert danach nur die Session als abgelaufen, das Profil bleibt deaktiviert.
- Der nächste Versuch liest `prior_enabled=False` und schreibt diesen Wert beim Abbruch zurück. Der Fehler verfestigt sich also.
- Repro: `kill -9` auf den Worker, danach erneut anmelden und abbrechen.
- Abhilfe: den Vorzustand in der Statusdatei persistieren und beim nächsten `start` bzw. `status` aufräumen. Alternativ ein separates `login_hold` statt `enabled`.

**5. Cancel- und Expiry-Prüfung laufen vor `proc.poll()`**
In derselben Schleifeniteration kann der Prozess bereits mit Code 0 beendet sein und neue Credentials in `authdir` geschrieben haben. Liegt gleichzeitig eine `.cancel`-Datei vor oder ist die TTL überschritten, endet die Session trotzdem als `cancelled` bzw. `expired`.
- Das Profil wird auf den Vorzustand zurückgesetzt, obwohl der Account bereits umgemeldet ist.
- Abbrechen während `verifying` nach erfolgreichem Ende wird stillschweigend ignoriert: `cancel_requested: true`, Ergebnis `succeeded`.
- Abhilfe: zuerst `poll()` auswerten. Abbruch nur akzeptieren, solange der Prozess läuft, und das in der Antwort korrekt melden.

## Wichtig

**6. 45-Sekunden-Heartbeat gegenüber blockierenden Phasen**
`status()` meldet `expired`, wenn `updated_at` älter als 45 s ist. Zwei Phasen schreiben keinen Heartbeat:
- **Nach `completed`:** `read_source` ist nicht begrenzt (Provider- oder Netzwerk-Abfrage). Die GUI sieht `expired`, beendet das Polling und zeigt einen Fehler, obwohl der Worker danach `succeeded` schreibt.
- **`file_lock(authdir/.native.lock)`:** Falls der Lock blockiert statt `WorkerBusy` zu werfen (bitte in `store.py` prüfen), gilt die Session nach 45 s als `expired`. Später läuft der Login trotzdem an, als „Zombie“ mit deaktiviertem Profil und ohne Client, der noch pollt.
- Abhilfe: ein Heartbeat-Thread während des gesamten Worker-Lebens, oder `read_source` mit Timeout.

**7. Namensnormalisierung bricht „Erneut anmelden“**
`start_login` normalisiert auf `[a-z0-9-]` und hängt bei führender Ziffer ein Präfix an. Erlaubt der Store Profilnamen wie `Work_1` oder `2nd`, legt „Erneut anmelden“ aus den Details ein *neues* Profil an, statt das bestehende anzumelden. Bei vorbefülltem Namen aus einem bestehenden Account darf nicht normalisiert werden.

**8. Claude-Login über Pipe-stdin ist nur per Fixture belegt**
Die echte `claude auth login` ist eine Ink/TTY-Anwendung. Möglich sind:
- „Raw mode not supported“ bei stdin ohne TTY,
- ein Code-Prompt, der eine Pipe nicht liest,
- Ausgaben, die das Regex `paste.*code` nicht treffen.

In jedem dieser Fälle greifen Punkt 2 bzw. 3. Der Fixture-Test beweist das nicht. Nötig ist mindestens ein manueller Smoke-Test mit der echten CLI auf Linux ohne TTY, besser ein PTY statt einer Pipe.

**9. Lebenszyklus des Remote-Workers**
Der Worker wird aus dem kurzlebigen RPC-Prozess der SSH-Session gestartet. Zu prüfen ist, ob `spawn_options(hidden=True)` unter POSIX `start_new_session=True` setzt. Ohne neue Session kann das Ende der SSH-Session den Worker beenden, zum Beispiel über die Prozessgruppe. Bei systemd-logind mit `KillUserProcesses=yes` sterben ihn alle Prozesse im Session-Scope, auch mit `setsid`. Dann greift Punkt 4. Der `login-reaper`-Thread ist im RPC-Prozess wirkungslos (harmlos).

**10. Account-Isolation unter macOS (lokal)**
Claude Code speichert OAuth-Credentials unter macOS im Schlüsselbund, nicht in `CLAUDE_CONFIG_DIR`. Zu verifizieren ist, dass zwei lokale Claude-Profile verschiedene Schlüsselbund-Einträge bekommen. Teilen sie sich einen, überschreibt Login B den Account A, und `verify` meldet für beide dieselbe E-Mail.

## Kleiner, aber reproduzierbar

- **Korrupte Statusdatei:** Eine einzelne kaputte `login-sessions/*.json` lässt `status()` in der Schleife von `start()` werfen. Danach sind alle neuen Logins blockiert.
- **Keine Bereinigung:** Sessiondateien werden nie entfernt, und `start` liest alle bei jedem Aufruf.
- **Verwirrende Fehlermeldung nach Timeout:** Nach einem SSH-Timeout bei `auth start` behält die GUI den Key. Ändert der Nutzer dann Name oder Anbieter, erscheint „Login key already belongs to another account“. Hier sollte ein neuer Key vergeben oder klar erklärt werden.
- **Erweiterte Verbindungseinstellungen:**
  - Die Feature-Prüfung `native-login-sessions` wird übersprungen. Alte Server werden akzeptiert, und `auth` scheitert erst später mit „RPC operation not allowed“.
  - Ein leeres Feld „Agent-Fleet-Datei“ scheitert an `validate`, obwohl nur das Datenverzeichnis gemeint war.
- **Entfernte Verbindung:** `show_login` ruft `RemoteConfig.get` ungeschützt im Tk-Callback auf. Wurde die Verbindung inzwischen entfernt, entsteht eine unbehandelte Exception und keine Fehlermeldung.
- **Device-Code-Erkennung:** `observe` nimmt den *ersten* Treffer von `[A-Z0-9]{4}-[A-Z0-9]{4,5}` im gesamten Puffer. Ein früheres Token gleicher Form, etwa eine ID in einer Bannerzeile, würde angezeigt. Besser die letzte Fundstelle nach der Device-URL verwenden.
- **Irreführende Meldung:** `WorkerBusy` aus dem Lock der Statusdatei meldet „Account wird verwendet“.
- **Überschriebene Nutzeränderung:** `finally` setzt `enabled=prior_enabled` blind. Hat der Nutzer das Profil zwischenzeitlich deaktiviert, wird das überschrieben.

## Positiv

- Codes laufen über RPC-stdin statt über die SSH-Kommandozeile, und `--code-file` ist remote gesperrt.
- Statusdateien werden atomar per `os.replace` mit 0600 geschrieben.
- URLs stehen auf einer Allowlist, Roh-Logs werden nicht persistiert.
- Der Start ist über `.start.lock` idempotent.
- Alte Antworten nach einem Zielwechsel werden über Epoch bzw. Token verworfen.

**Priorität:** 1, 3 und 4 zuerst. Sie hängen zusammen, ein persistierter Hold mit Aufräumen und einer einzigen Poll-Kette löst den Großteil. Danach 2 und 8 mit der echten CLI prüfen.

## Auflösung der Befunde

- Genau ein Login-Poll-Timer und ein laufender Poll pro Kontext; ältere Statusstände werden verworfen.
- Verlassen der Ansicht bzw. Rechnerwechsel bricht die Session ab. Beim Fensterschließen übernimmt ein entkoppelter Hilfsprozess. Cancel-vor-Start wird serverseitig als Tombstone berücksichtigt.
- Login verändert `enabled` vor Abschluss nicht; ein Abbruch überschreibt daher keine parallele Profil-Deaktivierung.
- Abgeschlossene native Prozesse werden vor Cancel/Expiry verarbeitet. Native Verifizierung und Metadatenleser haben bestehende 20-Sekunden-Timeouts; der Profil-Lock ist nachweislich nicht blockierend.
- Native Claude-Pipe-Eingabe mit vollständiger Code-/State-Form wurde real geprüft: ein ungültiger Testcode erzeugt die native Ablehnung und Exit 1. Geräte- und Browser-Flows starten mit beiden echten CLIs.
- Beschädigte alte Statusdateien blockieren neue Anmeldungen nicht. Späte Antworten und abweichende Namenseingaben erhalten getrennte Schlüssel.
- Linux nutzt verfügbare transient-systemd-User-Dienste für den Login, sonst einen entkoppelten Prozess. Auf persönlicher Unix-Vertrauenszone begrenzt.
- Für neue Codex-Profile ohne Konfiguration wird dateibasierte Speicherung eingestellt. Bestehende Profile und Konfigurationen bleiben erhalten. Unterschiedliche lokale Claude-Keychain-Identitäten sind nicht als vollständig live abgenommen behauptet; strukturierte Native-Statusabfragen werden ausgewertet.

Die konkreten Regressionen und die native UI-/SSH-/Linux-Kette sind ausführbar geprüft. Die vollständige Browser-Zustimmung eines neuen realen Kontos bleibt eine menschliche Aktion.
