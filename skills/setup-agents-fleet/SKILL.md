---
name: setup-agents-fleet
description: Installiert oder aktualisiert Agent Fleet auf Mac, Windows oder einem Linux-Server über SSH und führt durch native Codex-/Claude-Anmeldungen. Verwenden bei Ersteinrichtung, Remote-Verbindung oder zusätzlichen Accounts; für Aufträge den agent-fleet-Skill nutzen.
---

# Agent Fleet einrichten

Richte das Programm ein und begleite den Besitzer bis zu einer überprüften Anmeldung. Die App ist eine Account- und Kontingentübersicht; Aufträge führen Agenten über die CLI aus. Zugangsdaten bleiben beim nativen Anbieter auf dem ausführenden Rechner.

## Bestand und Ziel

Prüfe zuerst Betriebssystem, vorhandene `agent-fleet`-/`agent-pool`-Binaries bzw. `.pyz`, ihre Version, die persönliche App und `remote list`. Lies Status/Profile nur auf dem gewählten Ziel. Nutze vorhandene Antworten zu lokal/remote, SSH-Alias, Anbietern und gewünschten Accounts; frage nur nach einer noch fehlenden Entscheidung. Ein bestehender Servername ist kein allgemeiner Standard für andere Nutzer.

Wähle einen Pfad: lokaler Pool, reiner Remote-Client oder Linux-Server samt Client. Ein Remote-Client benötigt keine lokalen Provider-CLIs oder Provider-Logins. Lies für Installation und Updates [references/install.md](references/install.md), einschließlich des zur Plattform passenden Zweigs. Für Server zuerst Zugang, Installation, Pool, Workspace und unabhängigen Worker einrichten; anschließend den Client verbinden.

Installiere die aktuelle kompatible Version aus dem berechtigten Repository `the-fin-at/agent-pool`. Für die korrigierte Remote-Anmeldung und CLI-Exitcodes mindestens 0.4.1 verwenden. Vergleiche Downloads tatsächlich mit diesem Stand; ein als „latest“ bezeichnetes älteres Release genügt nicht. Erhalte bestehende Pools, Logins und fremde Dienste. Der Repository-Installer überschreibt vorhandene Ziele absichtlich nicht.

## Anmeldung begleiten

Lies [references/sign-in.md](references/sign-in.md). Öffne die installierte App auf dem gewählten lokalen/Remote-Ziel. Führe pro gewünschtem Account durch **Account hinzufügen**, Provider, Profilname und offizielle Browser-Zustimmung. Zusätzliche Accounts einzeln anmelden und jeweils den tatsächlich gewünschten Anbieter-Account im Browser wählen.

Technische Schritte selbst erledigen; nur die persönliche Anbieter-Anmeldung bleibt beim Besitzer. Wenn Zustimmung oder ein Browser-Rückgabecode fehlt, zeige genau diesen nächsten Schritt und lasse den Vorgang als „Anmeldung offen“ stehen. Eine startende Session, ein sichtbarer Gerätecode oder Exit 0 allein beweisen keine erfolgreiche Anmeldung. Nach Ablauf neu starten, statt einen alten Code erneut zu verwenden. Keine Passwörter oder Tokens im Chat, Repository oder Skill erfassen; Claude-Rückgabecodes in die maskierte App-Eingabe oder per CLI-stdin geben.

Vorhandene Server-Anmeldungen nur auf ausdrücklichen Wunsch über `profile add --auth-home` auf derselben Maschine einbinden. Keine Credentials kopieren. Der native Codex-Standardaccount in der lokalen Übersicht ist zunächst nur Anzeige, kein ausführendes Broker-Profil.

## Abnahme und Übergabe

- Lokaler Pool: `doctor` und `monitor --refresh`; Remote: `remote test <name>` und `--remote <name> status`. Remote-Status liest den Server-Cache; `--remote ... status --refresh` ist nicht unterstützt.
- Gewünschte Profile sind tatsächlich verbunden. Für Aufträge sind sie zusätzlich aktiviert und der Ziel-Worker ist online. Für eine reine lokale Übersicht ist kein Worker erforderlich. Fehlende Quoten bleiben unbekannt; Claude liefert keine vollständige private Usage-Abfrage.
- Ein echter Leseauftrag ist ein optionaler Abschlusstest mit bekanntem Workspace, begrenztem Timeout und ohne `--allow-edits`; er verbraucht Anbieter-Kontingent. Berichte `succeeded` erst nach Prüfung des Ergebnisses.
- Nenne installierte Versionen und Pfade, Verbindung, bestätigte Profile, Worker-Zustand sowie offene Browser-Schritte. Trenne „installiert“, „verbunden“ und „Auftrag geprüft“. Danach für Aufgaben den `agent-fleet`-Skill verwenden. Skills können eine neue Agenten-Sitzung zur Erkennung benötigen.
