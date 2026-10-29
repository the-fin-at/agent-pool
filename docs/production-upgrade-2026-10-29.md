# Produktionsupgrade auf Agent Fleet 0.5 · 29.10.2026

Am 29.10.2026 wurde der bestehende Linux-Pool auf `claw-remote` unter `clawadmin` mit ausdrücklicher Nutzerfreigabe von Python 0.4.2 auf das native Rust-ELF 0.5.0 umgestellt. Alle sieben bisherigen vollständigen Jobzeilen einschließlich IDs, Ergebnissen und Versuchen, sechs Profile (vier aktiviert), native Auth-Verzeichnisse und Workspaces blieben erhalten. Nach zwei zusätzlich autorisierten echten read-only Abnahmejobs enthielt der beobachtete Pool **neun erfolgreiche Jobs: sieben alte und zwei neue**.

Dieses interne Betriebsprotokoll beschreibt den vorhandenen privaten Projekt-Pool. Es ist kein öffentlicher Release und legt kein globales Ausführungsziel für andere Projekte fest. Quellstand: `the-fin-at/agent-pool@c47144087d3d7f665600ef0183af1c94dcd5180d`, Produktmerge `9f018a1ff90f9da0b8fba1a90e3ee02c67e142f7`, Dokumentationsbasis `79f2199b7d1201bd3ac12d178dcf82d143c387b5`. Der installierte und laufende ELF-Hash entspricht dem Linux-Release in [rust-tauri-validation.json](rust-tauri-validation.json).

## Ergebnis und Nachweisgrenzen

- Nativer 0.5.0-Worker, beobachtete PID `3543607`; SHA-256 `089affe0074cca081ad8b8a1190ee66c740a173573546c6a2c2aae530c6b99a8`. Zwei fortschreitende Heartbeats bei derselben PID und genau der erwartete Worker in der Service-Cgroup wurden unabhängig geprüft.
- Dieselbe Service-Unit, derselbe Pool-/Auth-Bestand und dieselben Workspaces. Unit-SHA-256 `4aa9065f3fe4e9a469cca7d56b7265da213b24d220d3e5641b683afd67b5f0e3`; der private Unit-Inhalt wird nicht veröffentlicht. Auth-Pfade, Inodes, Geräte und Modi blieben unverändert; keine Credential-Verzeichnisse kopiert.
- Der Quellvergleich vor Stopp, nach Stopp und nach Start ergab identische Job-/Profil-/Workspace-Inventare und Fingerprints. Ein unabhängiger Servercheck verglich alle sieben vollständigen Jobzeilen gegen die konsistente Sicherung; Client-RPC prüfte IDs und Ergebnisse erneut. **Live-SQLite und eine konsistente SQLite-Sicherung** bestanden die Integritätsprüfung. Es wird keine zweite Datenbanksicherung behauptet.
- OpenClaw- und VoxSTT-Dienste blieben aktiv mit denselben PIDs. Das Upgrade selbst verwendete keine Providerinferenz. Anschließend wurden genau zwei begrenzte echte Abnahmejobs über den neuen Produktionsworker ausgeführt.

Normalisierte Provenienz, vollständige Hashes und abgegrenzte Prüfresultate: [Upgrade-Nachweis](production-upgrade-2026-10-29-validation.json). Er enthält nur freigegebene Status-/Hashdaten; keine Prompts, Ergebnisinhalte, Account-E-Mails, Tokens oder privaten Unit-Inhalte.

## Zwei kontrollierte Umstellungsversuche

Alle folgenden Uhrzeiten gelten am 29.10.2026 in Europe/Vienna.

| Versuch | Beobachtetes Fenster | Ergebnis / Quelle |
| --- | --- | --- |
| Früher Stop-Guard-Abbruch | 07:23:36.276 bis 07:23:36.768, höchstens etwa 0,492 s | Der alte Python-Prozess endete auf SIGTERM mit Exit 130; systemd meldete `failed` statt des zunächst verlangten `inactive`. Der Guard brach vor Binärersatz und Datenbanksicherungsphase ab. Der alte Runtime wurde sofort wieder gestartet. Quelle ist der Ausführungsbericht im Chief-of-Staff-Chat, nicht die Eventdatei des später erfolgreichen Versuchs. |
| Erfolgreicher Wechsel | 07:24:24.916494 bis 07:24:25.462575, 0,546081 s zwischen Claim-Guard und frischem nativen Heartbeat | Nach geprüfter Ruhephase wurde der exakte erwartete alte Python-SIGTERM-Fall eng akzeptiert, der native ELF atomar installiert und derselbe Dienst gestartet. Quelle: gehashte `events.json` im Upgrade-Nachweis. |

Das erfolgreiche Schutzfenster beträgt gerundet etwa 0,546 s, konservativ unter 0,547 s. Es ist eine Betriebsbeobachtung vom Claim-Guard bis zum frischen Worker-Heartbeat und keine Modellgeschwindigkeitsmessung.

Die enge Stop-Regel verlangte für den bekannten alten Python-Fall `failed` / `exit-code` / `ExecMainCode=1` / `ExecMainStatus=130` sowie `MainPID=0`, verschwundene alte PID und leere Service-Cgroup. Vor dem Stopp gab es weder laufende Jobs noch native Login-Helfer; ein Datenbank-Claim-Guard verhinderte neue Claims. Andere Fehler bleiben Abbruchgründe. Die Unit wurde für diese Behandlung nicht verändert. Ein produktiver Rollback nach erfolgtem Rust-Start war nicht erforderlich; der frühe Wiederanlauf des alten Programms fand vor dem Binärersatz statt.

## Echte native Provider-Abnahme

Nach dem unabhängigen Post-Upgrade-Check liefen genau diese zwei Jobs über den Produktions-Rustworker. Jeder durfte ausschließlich lesen, höchstens 90 Sekunden und genau einen Versuch ausführen. Profil und Modell waren ungepinnt; der Broker wählte innerhalb des ausdrücklich angeforderten Providers.

| Provider | Job / Profil | Ergebnis | Beobachtete Queue-plus-Ausführungszeit |
| --- | --- | --- | --- |
| Codex | `bce22f54c2434530a1d6cd6133fa52c7` / `server-codex` | succeeded, ein Versuch, erwartetes Dateiergebnis exakt geprüft | 13,027 s |
| Claude | `3b4db891227c4e2e810718171513ddf3` / `server-claude` | succeeded, ein Versuch, erwartetes Dateiergebnis exakt geprüft | 17,872 s |

Die offiziellen nativen Programme meldeten `codex-cli 0.155.0` und `2.1.312 (Claude Code)`. `model: null` bedeutet nativer Standard; die aufgelöste Modellidentität wird von der Job-API nicht geliefert und wird hier nicht erfunden. Die Agenten lasen eigene synthetische Serverdateien mit Nonces, die im Prompt fehlten. Erwartungs- und Ergebnis-Hashes stimmten überein; die Dateien blieben unverändert. Prompts, Nonces und rohe Ergebnisse werden nicht kopiert.

Die sieben alten vollständigen Jobs blieben unverändert. Die Abnahme erzeugte genau zwei neue Jobzeilen und eigene synthetische Fixture-Dateien; Auth-, Login-, Profil- und Servicekonfiguration wurden dabei nicht geändert. Keine nativen Kindprozesse blieben zurück. Der Endstand dieser Abnahme war neun `succeeded`-Jobs. Die beiden Zeiten sind Einzelbeobachtungen einschließlich Queue und Providerlauf; sie belegen weder einen allgemeinen Performance-Grenzwert noch einen LLM-Benchmark. [Sanitisierter Provider-Nachweis](native-provider-smokes-validation.json).

## Wiederholen und Rücknahme vorbereiten

Für eine Wiederholung zuerst Projektziel, SSH-Verbindung, Pool und Workspace ausdrücklich aus dem aktuellen Auftrag bestimmen. Ein vorhandener Remote ist keine globale Zielvorgabe. Status und inventarisierte IDs/Versuche/Ergebnis-Hashes lassen sich über die öffentliche CLI/RPC-Grenze erneut vergleichen:

```sh
agent-fleet --remote <projektverbindung> status
agent-fleet --remote <projektverbindung> job list
ssh <projekt-ssh-alias> 'systemctl --user show agent-fleet.service -p ActiveState -p SubState -p MainPID'
```

Vor jeder weiteren Umstellung den exakten Kandidatenhash und die bestehende Unit prüfen, eine aktuelle konsistente SQLite-Inventur/Sicherung anfertigen und aktive Ausführungen kontrolliert behandeln. Wartende Jobs bleiben bestehen. Fehler-/Lastinjektion gehört in isolierte Pools; echte Inferenz bleibt ein ausdrücklich begrenzter eigener Abnahmeauftrag.

Die private Sicherung dieses Wechsels liegt auf demselben Server unter `~/.local/share/agent-fleet-upgrade-backups/20261029T062424Z` (Verzeichnis 0700, SQLite-Datei 0600). Sie enthält das alte Programm `agent-fleet.0.4.2`, die gehashte Unit und **eine** konsistente `queue.sqlite3`, keine kopierten Auth-Verzeichnisse. Das alte Programm hat SHA-256 `24b1736f942fa9873a54e271c2803b74383a9832829bbbc69ed6cfec133f1348`, meldet 0.4.2 und konnte die damaligen sieben Sicherungsjobs lesen.

Eine spätere Rücknahme ist **programmbezogen und erhält die aktuelle Live-Datenbank**:

1. Neue Claims kontrolliert anhalten; aktive Jobs/Login-Kinder beenden lassen oder bei Unklarheit prüfen. Lockhalter und fremde Dienste bewahren; wartende Arbeit nicht leeren.
2. Den Rücknahmekandidaten zunächst gegen eine aktuelle konsistente Kopie mit allen inzwischen eingetroffenen Jobs prüfen. Die alte Sicherung mit sieben Jobs beweist nicht allein den Zustand nach späteren Ankünften.
3. Den eigenen Worker stoppen; PID/Cgroup und Jobzustände eindeutig prüfen. Erst bei tatsächlicher Ruhe das gespeicherte, hashgeprüfte Programm am bisherigen Executable-Pfad atomar ersetzen.
4. Dieselbe Unit mit demselben Home starten und Gesundheit, Version, vollständige aktuelle Jobzeilen/Ergebnisse, Profile/Auth-Verzeichnisse und Workspaces vergleichen.
5. **Keinen alten Datenbanksnapshot zurückspielen.** Er würde neue Jobs verwerfen. Bei inkompatiblem Kandidaten oder unklarem Ausführungszustand Live-Daten erhalten und untersuchen; kein automatischer Replay von `needs_review`.

Diese Dokumentation behauptet keinen bereits bestandenen vollständigen Upgrade-/Rollback-Fehlerkatalog mit befüllter Queue. Das isolierte Gate [Issue #24](https://github.com/the-fin-at/agent-pool/issues/24) und die native Performancearbeit [Issue #25](https://github.com/the-fin-at/agent-pool/issues/25) waren beim Checkpoint in Bearbeitung. Windows blieb auf ausdrücklichen Nutzerwunsch mangels verfügbarer Maschine zeitlich zurückgestellt und als Gate offen. Hosted CI blieb vor Start durch Billing blockiert; eine öffentliche Vertriebs-/Signierungsentscheidung und 1.0-Freigabe folgen daraus nicht.
