# Agent Fleet Desktop · Rust und Tauri

Die native App verwendet den Rust-Kern gemeinsam mit der CLI. React und TypeScript stellen die THE-FIN-Oberfläche dar: warme Flächen, Seitenleiste, Albert Sans, Kontingentkreise und Wochenbalken. Die App dient der Übersicht, Verbindungsverwaltung und nativen Anmeldung. Aufträge erteilen Agenten über CLI und Skills; ein separater Worker führt sie aus.

## Bauen und installieren

Rust gemäß `rust-toolchain.toml`, Node.js 24 und die [Tauri-Systemvoraussetzungen](https://v2.tauri.app/start/prerequisites/) installieren. Auf Mac genügen für Desktop-Builds die Xcode Command Line Tools. Windows benötigt unter anderem die C++-Buildwerkzeuge und WebView2.

```sh
cargo build -p fleet-cli --release --locked
cd desktop
npm ci
npm run tauri build
```

Die Mac-App liegt in `target/release/bundle/macos/Agent Fleet.app`, Windows-Installer unter `target/release/bundle`. Native Pakete jeweils auf dem Zielsystem bauen. Auf dem Mac installiert `sh scripts/install_native.sh --desktop` aus dem Repository-Stamm App und CLI. Bei bestehenden Installationen erst vergleichen, dann mit `--replace` ersetzen; die vorige Installation bleibt als Backup erhalten. Unter Windows installiert `scripts/install_native.ps1` die CLI; den erzeugten Desktop-Installer separat ausführen.

Unter Windows findet `agent-fleet desktop` die normale NSIS-Installation unter `%LOCALAPPDATA%\\Agent Fleet`. Bei eigenen Installationsorten `AGENT_FLEET_DESKTOP_BIN` auf die native Desktop-EXE setzen. Auf Mac werden der persönliche und der systemweite Programme-Ordner geprüft.

Die fertige App enthält keinen Python-/Tk-Unterbau. Benutzer brauchen keine Rust- oder Node-Entwicklungsumgebung. Provider-CLIs und Logins richten sie je Zielrechner separat ein. Ältere veröffentlichte `.pyzw`- und PyInstaller-Pakete bleiben ältere Python-Versionen.

## Übersicht und Anmeldung

Oben zwischen Lokal und Remote wechseln; Remote führt zunächst zu den gespeicherten SSH-Verbindungen. Die Seitenleiste filtert Accounts nach Provider. Suche und „Alle Profile anzeigen“ machen auch pausierte Profile auffindbar. Details zeigen Quoten, Datenstand und mögliche Sperren. Der bestehende Codex-Hauptaccount ist eine Anzeigequelle und wird dadurch nicht automatisch für Aufträge aktiviert.

Kreise zeigen den freien Anteil eines tatsächlich beobachteten 5-Stunden-Fensters, Wochenbalken das freie Wochenkontingent. Das Fenster ist keine verbleibende Rechenzeit. Modelllimits bleiben separat sichtbar. Fehlende Daten und überschrittene Resets gelten als unbekannt bzw. nicht aktuell, bis eine neue Beobachtung vorliegt. Claude-Werte stammen aus gespeicherten nativen CLI-Ereignissen; die App fragt keine privaten Usage-HTTP-Endpunkte ab.

Neue Accounts melden sich über die offizielle Provider-CLI an. Browserseiten müssen zu den erlaubten offiziellen HTTPS-Adressen gehören. Bei Claude wird ein gegebenenfalls benötigter Code verdeckt eingegeben und an den nativen Loginprozess weitergereicht. Native Anmeldedaten bleiben in ihren vorhandenen Verzeichnissen. Ein Abbruch beendet die betreffende Anmeldung, keinen Queue-Worker.

## Daten und Abnahme

Desktop und CLI verwenden weiter den bisherigen `AgentPool`-Pfad und dieselbe SQLite-Datenbank. Bestehende IDs, Ergebnisse, SSH-Verbindungen und native Account-Verzeichnisse bleiben erhalten. Die [Migrationsdokumentation](rust-migration.md) nennt Datenpfade, Buildbefehle und getrennte Nachweise für Kern, Datenkompatibilität, echte WebView, Remote-Verbindung, CI und Plattformen.
