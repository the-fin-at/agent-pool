# Rust-/Tauri-Umstellung

Agent Fleet 0.5 verwendet einen nativen Rust-Kern und eine Tauri-2-App. Die neue Laufzeit benötigt keinen Python-Interpreter. Der bisherige Python-Quellstand bleibt als Kompatibilitätsreferenz und für ältere Server erhalten.

## Daten bleiben an Ort und Stelle

- Mac: `~/Library/Application Support/AgentPool`
- Windows: `%LOCALAPPDATA%\AgentPool`
- Linux: `~/.local/share/agent-pool`
- Individuelle Pools: `--home` oder `AGENT_POOL_HOME`

Die Namen sind absichtlich unverändert. Profile, angehängte native Account-Verzeichnisse, `queue.sqlite3`, Auftrags-IDs, Berichte, Zustände, Auftragsschlüssel und `remotes.json` werden weiterverwendet. Native Provider-Logins bleiben in ihren vorhandenen Verzeichnissen. Die App kopiert keine Zugangsdaten und legt keine Ersatzaccounts an.

Die SQLite-Struktur und RPC-Version 1 bleiben kompatibel. Rust- und Python-Worker verwenden dieselbe `worker.lock`; Accountprozesse verwenden dieselbe `.native.lock`. Für einen Pool läuft weiterhin genau ein Worker. Nach einem unerwarteten Abbruch bleibt die Prüfung eines `needs_review`-Auftrags erforderlich. Ein Upgrade darf einen solchen Auftrag nicht automatisch wiederholen.

Eine bestehende Serverinstallation kann zunächst weiterlaufen: Der neue Rust-Client spricht weiterhin das bisherige SSH-/RPC-Protokoll. Server-Upgrades erfolgen separat mit demselben Poolpfad. Keine laufenden Providerprozesse oder fremden Dienste für die Desktop-Umstellung beenden.

## Bauen

Entwicklung benötigt Rust gemäß `rust-toolchain.toml`, Node.js 24 und die Systemvoraussetzungen von Tauri 2. Diese Werkzeuge sind auf dem Rechner des späteren App-Nutzers nicht erforderlich.

```sh
cargo build -p fleet-cli --release
cd desktop
npm ci
npm run build
npm run tauri build
```

Die Rust-CLI liegt in `target/release/agent-fleet` (Windows `.exe`), die App/Installer in `target/release/bundle/`. Die nativen Codex-/Claude-CLIs werden wie bisher separat installiert. Eine reine Remote-App braucht keine lokalen Provider-Anmeldungen.

## Prüfen

```sh
cargo test -p fleet-core -p fleet-cli
cargo build -p fleet-cli --examples
cargo build -p fleet-cli
python3 scripts/test_rust_compatibility.py
cd desktop
npm test
npm run build
```

Die Python-Prüfung verwendet die bisherige Implementierung als unabhängige Datenbank-/Protokollreferenz. Testpools und kontrollierte Provider enthalten keine echten Zugangsdaten und führen keine Inferenz aus. Produktive Accounts werden ausschließlich für begrenzte Metadaten-/Statusprüfungen verwendet. Echte Plattformabnahmen werden im Migrationsnachweis von simulierten Provider- und Browserprüfungen getrennt dokumentiert.

## Abnahme auf Basis ddbc859

Die gemeinsame Basis enthält PR13 (vollständige Claude-Fenster), PR15/18 (automatische Accountwahl und projektbezogenes Ziel), PR21 (belegte native Accounts überspringen) und den getrennt gepflegten 1.0-Plan. Der Rust-Kern hat dieselben Grenzen für Anbieter, Modell, Bucket und explizite Profilbindung. Belegte Accounts verbrauchen keinen Versuch und ändern weder Holds noch `last_used`; ein anderer bereiter Account oder späterer unabhängiger Auftrag kommt weiter.

| Ausgeführte Prüfung | Ergebnis |
| --- | --- |
| Python-Referenz mit echtem Tk auf Mac | 145 Tests bestanden |
| Rust-Kern | 85 Tests bestanden |
| Tauri-Bridge/URL-Grenzen | 2 Tests bestanden |
| React-Flows, Kontextwechsel und Fehler | 22 Tests bestanden |
| Typprüfung, Produktionsbuild, Clippy mit `-D warnings` | bestanden |
| npm-Audit | 0 gemeldete Schwachstellen |
| Cross-Language-/Prozesstests | je 23 auf Mac, lokalem Linux-x86_64-Container und echtem Linux-Host bestanden |
| Kontrollierte Last | je 100 eindeutige Aufträge und native Ausführungen; Mac 3,411 s, Container 2,995 s, echter Linux-Host 2,511 s |
| Rust-Client zu bestehendem Python 0.4.2-Server | 7 bestehende IDs und gespeicherter Bericht identisch; Cache-only |
| Rust-Client zu nativem Rust 0.5-Server über echtes SSH | kompatibel; unterbrochene Antwort nach Commit und identischer Retry erzeugen genau einen Auftrag |
| Mac-Releasepaket | eigenständige arm64-App, 15,59 MiB, lokale Ad-hoc-Signatur deep/strict gültig |

Die Lastwerte messen Queue und kontrollierte native Testprozesse; sie sind keine Modellgeschwindigkeit. Linux-Ausführung und Lost-ACK lagen ausschließlich in einem privaten Testordner. Der produktive Serverworker und echte Accounts blieben unverändert. Die native Rust-CLI konnte den bestehenden lokalen Pool mit 4 Profilen öffnen, ohne Profile/Jobs zu verändern; ältere Ergebnisse werden zusätzlich durch die Datenbankfixtures belegt.

## Native Oberfläche und Grenzen

Der finale echte macOS-WKWebView-Lauf bestand 23 Prüfschritte: gespeicherte Daten/Ergebnis, exakte Quotenwerte aus Rust, Kreis-Ausrichtung bei langen E-Mail-Adressen, Filter/Suche/Details, native Codex-Geräteanmeldung mit Abbruch und Claude-Codeeingabe bis zur bestätigten Anmeldung. Beide kontrollierten nativen Login-Kinder waren danach beendet. [Finale native Fensteraufnahme mit Testaccounts](../design/2026-10-28/rust-tauri/native-overview.png).

Zwischenläufe wurden durch eine gesperrte Mac-Sitzung blockiert: IPC blieb erreichbar, WebView-Timer stoppten. Die Diagnose wurde über minimale native IPC-Probe, Ladehook und CGSession belegt; nach Entsperren bestand der vollständige Lauf. Der Harness prüft nun vorab den Sitzungsstatus und endet bei gesperrter/fehlender Konsolensitzung mit Code 77, ohne App oder Provider zu starten. Temporäre Diagnoseinstrumentierung ist entfernt. Auf entsperrtem Mac wiederholen:

```sh
cargo build -p fleet-cli --examples --locked
cargo build -p agent-fleet-desktop --features custom-protocol --locked
python3 scripts/test_native_desktop.py --output /tmp/fleet-native-qa
```

Der Diagnosehook ist ausschließlich im Debug-Build enthalten; das optimierte Release enthält ihn nicht. Es gab keine Änderung an produktiven Credentials. Ein neuer echter Anbieter-Login braucht weiterhin die persönliche Browser-Zustimmung.

Windows ist als Ziel implementiert und als CI-Matrix vorbereitet, aber hier nicht nativ ausgeführt. Mac- und Linux-Nachweise sind keine Windows-Abnahme. Das Mac-Paket ist lokal signiert und nicht öffentlich notarisiert; es wird als `.app` gebaut, der Windows-Build erzeugt NSIS. GitHub-CI wird getrennt vom lokalen Ergebnis dokumentiert. Maschinenlesbare Nachweise: [rust-tauri-validation.json](rust-tauri-validation.json).

Der geprüfte Implementierungsstand ist `c47144087d3d7f665600ef0183af1c94dcd5180d`. Zwei unabhängige Reviews fanden je einen P2; beide wurden behoben und erneut ohne offene Befunde geprüft. [Reviewnachweis](reviews/rust-tauri-review.md). Die abschließende native Fensteraufnahme stammt ebenfalls aus diesem Stand.

GitHub startete die CI-Jobs dieses Kandidaten wegen fehlgeschlagener Zahlungen beziehungsweise des Ausgabenlimits der Organisation nicht. Dies ist keine grüne CI und keine Windows-Abnahme. [Nativer Workflow](https://github.com/the-fin-at/agent-pool/actions/runs/40778503951), [Python-Referenzworkflow](https://github.com/the-fin-at/agent-pool/actions/runs/40778503882).
