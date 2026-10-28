# Durch die Anmeldung führen

## Ziel und Profile

In der App zuerst **Lokal** oder **Remote → gewünschte Verbindung** öffnen. Für Remote müssen CLI und Worker auf dem Server eingerichtet sein; neue Accounts werden dort gespeichert, der Browser darf auf dem Client laufen. Native Provider-CLIs sind auf dem Client dafür nicht nötig.

**Account hinzufügen** wählen, Codex/Claude und einen verständlichen Profilnamen setzen. Bei vorbereiteten Profilen **Alle Profile anzeigen** aktivieren und das gewünschte Profil anmelden. Bereits verbundene Accounts nach Prüfung wiederverwenden. Bei jeder zusätzlichen Anmeldung den Besitzer ausdrücklich darauf achten lassen, im Browser den gewünschten Account zu wählen; ein neuer Profilname erzeugt kein neues Abo.

## Codex

Die App startet `codex login --device-auth`. Gerätecode kopieren, über **Im Browser anmelden** die offizielle Seite öffnen und den Code dort bestätigen. Der Besitzer übernimmt gegebenenfalls Passwort/MFA und Workspace-Auswahl selbst. Falls Device-Login beim Anbieter deaktiviert ist, dessen aktuelle Sicherheits-/Workspace-Einstellung anhand der offiziellen Dokumentation prüfen; alternativ den nativen interaktiven Login auf der ausführenden Maschine verwenden.

Erfolg erst nach bestätigtem nativen ChatGPT-Login und aktualisiertem Account-Stand. API-Key-Anmeldung erfüllt diesen Abonnementpfad nicht. Neue getrennte Codex-Profile ohne vorhandene Konfiguration erhalten dateibasierte Credential-Speicherung für Headless-Betrieb. Vorhandene Konfigurationen erhalten.

## Claude

Die App verwendet `claude auth login --claudeai`. Offiziellen Browser-Link öffnen. Gibt der Browser einen Rückgabecode aus, den **vollständigen** Code in das maskierte Feld der App einfügen und **Anmeldung abschließen** wählen. Insbesondere beim Remote-Server darf der Client-Browser keinen lokalen Server-Callback erreichen müssen.

Die native CLI muss das angeforderte `configDirectory` in `auth status` bestätigen. Meldet die App fehlende Unterstützung, CLI auf dem ausführenden Rechner aktualisieren oder ein separates Profil mit neuem Namen über `profile add <name> --provider claude --binary <aktueller-absoluter-pfad>` registrieren; einen zufällig bestehenden globalen Login nicht als Erfolg des neuen Profils behandeln. Erfolg erfordert `loggedIn` und die native Claude-Abonnement-Anmeldung; fehlende Usage-Werte bleiben unbekannt.

## Wenn kein Desktop verfügbar ist

Native interaktive Anmeldung direkt auf dem ausführenden Rechner:

```sh
agent-fleet login codex-1 --device-auth
agent-fleet login claude-1
```

Für browsergestützte Remote-Anmeldung ohne SSH-Terminal pro Account die Session-Schnittstelle nutzen:

```sh
agent-fleet --remote zentral auth start arbeit --provider codex --key NEUER_UUID_HEX
agent-fleet --remote zentral auth get SESSION_ID
agent-fleet --remote zentral auth cancel SESSION_ID
```

`NEUER_UUID_HEX` durch einen frisch erzeugten 32-stelligen UUID-Hex-Schlüssel ersetzen. Bei unklarer Start-Antwort denselben Schlüssel mit identischen Parametern wiederverwenden; bei Fehler/Abbruch/Expiry für einen neuen Versuch einen neuen Schlüssel verwenden. Für Claude bei `awaiting_code` den vollständigen Rückgabecode per `auth input SESSION_ID --code-file -` über stdin auf dem Client eingeben. Der Code wird nicht als Shell-Argument, Datei im Repository oder Chat-Nachricht übermittelt. Lokale Sessions verwenden dieselben Befehle ohne `--remote`.

Es sind zeitlich begrenzte Sessions. Bei fehlender menschlicher Zustimmung Session-ID, Ziel und nächsten Browser-Schritt nennen, nicht auf unbestimmte Zeit pollen oder Erfolg behaupten. Alte/abgebrochene Sessions per `auth cancel` beenden; zum Fortsetzen Status prüfen und bei Ablauf eine neue Session starten. Die App bricht einen laufenden Login beim Verlassen der Ansicht ab.

## Tatsächlichen Abschluss prüfen

`succeeded` in der Login-Session und anschließend verbundenen Account im lokalen Monitor bzw. Remote-Status prüfen. Nach bestätigter Session aktiviert die App das Profil. Beim nativen interaktiven Login zusätzlich den aktuellen Account-/Quotenstand aktualisieren und prüfen. Ein belegtes Profil meldet „busy“; vor erneuter Anmeldung warten, statt dessen laufenden Auftrag abzubrechen.

Anmeldung für jeden gewünschten Account wiederholen. Kontingente gelten weiterhin pro Account. Ein Account ohne bekannte Quoten ist kein Beweis für freie oder ausgeschöpfte Kontingente. Im Abschluss bestätigte und noch offene Accounts getrennt nennen und den nächsten Browser-Schritt konkret lassen.
