# Private native Paketvorbereitung

Für die interne Verteilung sind zwei native **0.5.0**-Archive vorbereitet: macOS arm64 mit CLI und `.app`, Linux x86_64 mit CLI. Es wurde kein GitHub-Release angelegt, kein Asset hochgeladen und kein „latest“-Release geändert. Die öffentliche Verteilung und die endgültige 1.0-Freigabe bleiben eigene Entscheidungen. Windows ist weiterhin offen.

Der Helfer `scripts/package_native_release.py` verpackt bereits geprüfte Programme. Er baut nichts, startet keine App und greift auf keinen Pool oder Provider zu. Die Programme benötigen beim Anwender weder Python noch Rust/Node. Nur der Paketiernachweis benötigt Python 3.12 oder neuer auf dem jeweiligen nativen Zielhost sowie auf Mac `codesign`.

## Eingaben und Paketvertrag

Explizit übergeben werden das native CLI-Artefakt, auf Mac die `.app`, der vertrauenswürdige Referenznachweis und ein **noch nicht vorhandenes** Ausgabeverzeichnis. Die Referenz muss aus einem geprüften Checkout stammen; ein mitgelieferter oder selbst veränderter Hashnachweis beweist keine Authentizität. Aktuell werden ausschließlich die in [rust-tauri-validation.json](rust-tauri-validation.json) belegten 0.5.0-Artefakte unterstützt.

Vor dem ersten Programmaufruf prüft der Helfer den exakten SHA-256, den nativen Dateikopf und die Architektur. Danach prüft er die CLI-Ausgabe `--version`. Das macOS-Bundle muss genau die geprüfte Struktur aus `Info.plist`, Desktop-Executable, `app.icns` und `CodeResources` enthalten. Zusätzliche Dateien und Verzeichnisse werden abgelehnt. Bundle-Version, Executable-Hash und Deep/Strict-Signatur müssen stimmen. Das Desktop-Executable wird für diese Prüfung nicht gestartet. Sichere interne Symlinks werden erhalten; absolute, aus dem Bundle führende oder hängende Links werden abgelehnt. Das tatsächlich geprüfte Bundle enthält keine Symlinks.

Das Archiv übernimmt den vorhandenen [Installervertrag](../scripts/install_native.sh):

```text
scripts/install_native.sh
target/release/agent-fleet
target/release/bundle/macos/Agent Fleet.app/   # nur macOS
```

Die native CLI heißt `agent-fleet`; die Pakete erfinden keinen zusätzlichen Alias. Authentifizierung, Pool, Datenbank, Profile, Logs, Quellcheckout und Provider-Programme gehören nicht zum Paket. Das mitgelieferte Installerskript stammt unverändert aus dem geprüften Checkout; sein Hash ist im Paketmanifest enthalten.

## Wiederholen

Auf dem passenden nativen Host aus einem geprüften Checkout ausführen; die Beispielpfade durch die eigenen geprüften Artefakte ersetzen:

```sh
python3 scripts/package_native_release.py \
  --reference docs/rust-tauri-validation.json \
  --platform macos-arm64 \
  --cli /pfad/zum/geprueften/agent-fleet \
  --app '/pfad/zur/geprueften/Agent Fleet.app' \
  --output /bestehender/staging-ordner/macos-run1
```

Auf Linux `--platform linux-x86_64` verwenden und `--app` weglassen. Beide Varianten müssen auf dem jeweiligen nativen Host laufen. Für einen zweiten Lauf nur den Ausgabepfad ändern. Bestehende Ausgaben, auch leere Verzeichnisse und Symlinks, bleiben unverändert und werden abgelehnt. Ausgaben innerhalb der Eingabe-App werden ebenfalls vor Änderungen abgelehnt.

Jeder Lauf erzeugt ein `.tar.gz`, `SHA256SUMS` und `manifest.json`. Der Helfer sortiert die Einträge, setzt Archivzeiten und Eigentümer auf null und lässt Gzip-Dateiname und Eigentümernamen leer. Modi und sichere Links bleiben erhalten. Er extrahiert das eigene Archiv mit dem sicheren Python-Datenfilter in ein neues temporäres Verzeichnis und prüft sämtliche Dateihashes, Modi, Links, native CLI-Version und auf Mac erneut die vollständige Signatur. Bei der Extraktion werden die geprüften Verzeichnismodi nach dem Datenfilter wiederhergestellt, damit die Host-Umask den Vergleich nicht verändert.

Die öffentliche CLI lässt sich einschließlich tatsächlicher zweifacher Paketerzeugung prüfen:

```sh
# Operator-JSON außerhalb des wiederverwendbaren Codes anlegen:
# {"reference":"/checkout/docs/rust-tauri-validation.json",
#  "platform":"macos-arm64", "cli":"/artefakte/agent-fleet",
#  "app":"/artefakte/Agent Fleet.app", "cli_sha256":"<gepruefter Referenzhash>"}
FLEET_PACKAGE_INPUTS=/pfad/zu/operator-inputs.json \
  python3 tests/real-host/test_native_package.py
```

Ohne explizite Artefakte laufen die unabhängigen Negativprüfungen; der tatsächliche Paket-Roundtrip wird dann übersprungen. Linux lässt nur die beiden Mac-Bundle-Prüfungen aus. Die Tests verwenden für erfolgreiche Läufe ausschließlich die explizit freigegebenen echten Artefakte.

## Geprüfte Ergebnisse am 29. Oktober 2026

| Paket | Bytes | SHA-256 |
| --- | ---: | --- |
| `agent-fleet-0.5.0-macos-arm64.tar.gz` | 8.320.663 | `2c13e5567ca22a2119fbae6f0bb56f8979ca30681f8e18baf1528a12d0c58ac4` |
| `agent-fleet-0.5.0-linux-x86_64.tar.gz` | 2.583.987 | `3b69407f5b1e80172dc5508fee47f5e1bbf78fa061304f4507f787d3484d36b5` |

Je zwei Läufe auf dem tatsächlichen nativen Host lieferten identische Archive, Manifeste und Prüfsummenlisten. Mac: sieben Tests bestanden. Linux: fünf bestanden, zwei ausschließlich Mac betreffende Prüfungen übersprungen. Sämtliche extrahierten Einträge stimmen mit den Eingaben überein. Beide extrahierten CLIs melden `0.5.0`; die extrahierte Mac-App besteht `codesign --verify --deep --strict`. Die Dateiköpfe belegen Mach-O arm64 und ELF64 x86_64; die Linux-Datei ist static-pie. Die Mac-Signatur ist lokal ad-hoc, die App ist nicht notarisiert.

Die Programme stammen aus dem geprüften Implementierungsstand `c47144087d3d7f665600ef0183af1c94dcd5180d`, integriert mit PR #22 / Merge `9f018a1ff90f9da0b8fba1a90e3ee02c67e142f7`. Paketierbasis ist `79f2199b7d1201bd3ac12d178dcf82d143c387b5`. Rust war auf `1.96.1` festgelegt. Der erhaltene Mac-Buildcache nennt `rustc 1.96.1 (31fca3adb 2026-06-26)`, LLVM 22.1.2 und `aarch64-apple-darwin`; Linux stammt aus dem zuvor geprüften Rust-1.96.1-Alpine-Build für linux/amd64. Ein unveränderlicher Image-Digest des damaligen Linux-Buildcontainers ist im übernommenen Nachweis nicht festgehalten. Für diese Pakete wurde kein Compiler neu ausgeführt.

Der [maschinenlesbare Nachweis](native-distribution-validation.json) enthält vollständige Mitgliederlisten, Original- und Archivhashes, Toolchain- und Prüfumfang. Die lokalen Dateien liegen derzeit unter `/private/tmp/fleet-native-packages-20261029/`, je in `macos-run1`, `macos-run2`, `linux-run1` und `linux-run2`. Diese temporären Pfade sind Arbeitsnachweise und müssen vor einer späteren Verteilung an einen freigegebenen dauerhaften Ort übernommen werden.

## Installation aus einem freigegebenen Paket

Den Archivhash gegen den separat geprüften Nachweis vergleichen und ausschließlich das geprüfte Archiv in einen neuen leeren Staging-Ordner extrahieren. Dort `sh scripts/install_native.sh --desktop` auf Mac beziehungsweise `sh scripts/install_native.sh` auf Linux ausführen. Bei bestehenden Programmen zuerst Version, Dienste und laufende Aufträge prüfen; nach kontrolliertem Vergleich `--replace` verwenden. Der vorhandene Installer behält die vorige Programmdatei beziehungsweise App als Backup und verändert den Pool nicht. Ein Worker-Upgrade mit laufenden Aufträgen folgt weiterhin dem gesonderten Upgrade-/Rollback-Verfahren. Die Paketprüfung allein autorisiert keine Installation und startet keinen Dienst.

Belegt ist die wiederholbare **Paketierung derselben geprüften Programme pro nativem Host**. Ein unabhängiger kalter Compiler-Build, bytegleiche Compilerergebnisse, Notarisierung, DMG-Abnahme, Windows-Abnahme und die endgültige 1.0-Veröffentlichung sind damit nicht nachgewiesen.

## Private draft checkpoint — 29 October 2026

After package PR #30 merged at `cbc73174280b51ba373fcdce276c262d37f242bc`, the six reviewed archive/manifest/checksum assets were uploaded to the private [0.5 draft release](https://github.com/the-fin-at/agent-pool/releases/tag/untagged-1a61c45f5d211320096b), release ID `427556636`, targeting product merge `9f018a1ff90f9da0b8fba1a90e3ee02c67e142f7`. Both metadata asset names are platform-qualified for each platform; their bytes were unchanged. Downloaded bytes, sizes and GitHub SHA-256 digests matched the reviewed local inputs for every asset. The [normalized readback evidence](release-operations-2026-10-29-validation.json) records asset IDs and hashes without local temporary paths.

At this observation the repository remained private, the release had `draft=true` and `published_at=null`, and published Latest remained `v0.3.0`. This draft supplied a durable private review location for the prepared assets; it did not publish them, install another copy, establish a 1.0 distribution decision or satisfy the remaining signing/Windows gates.
