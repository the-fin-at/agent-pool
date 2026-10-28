# Rust-/Tauri-Review

Basis: `ddbc859cbecb7c7af80fc2be918574d34d0099d7`.
Implementierung: `131278bf7266a05c9fb580c7a01559c91ee98d7a`.
Erneut geprüfter Stand mit beiden Korrekturen: `c47144087d3d7f665600ef0183af1c94dcd5180d`.
Nach diesem Stand folgen ausschließlich Nachweisdokumente und die finale native Fensteraufnahme.

Zwei getrennte Reviewer prüften Standards und Spezifikation read-only. Sie führten keine eigenen Builds aus; die unten genannten Tests wurden vom Hauptagenten separat ausgeführt.

## Standards

Keine dokumentierten Standardverletzungen oder berichtenswerten heuristischen Auffälligkeiten. Ein zusätzlicher P2 zur Fehlerbehandlung: `run_native` behandelte auch I/O-Fehler am nativen Lock als belegten Account und konnte endlos warten.

Korrektur: Nur echte Lockkonflikte werden `WorkerBusy`; andere Fehler bleiben erhalten und führen zu `needs_review`. Ein neues Szenario mit unbrauchbarem Lock wurde zunächst rot und nach der Korrektur grün ausgeführt. Es belegt, dass weder ein Provider startet noch eine Wiederholungsschleife entsteht.

Abschluss des Standards-Reviewers: „Neue relevante Befunde: 0.“ Der gesamte Korrekturvergleich wurde erneut gelesen; auch die engere Fehlerklassifikation in `Lease::acquire` wurde geprüft.

## Spezifikation

Ein P2: Eine verspätete Antwort beim Speichern der Verbindung A konnte nach Verlassen des Formulars und Öffnen von B die neue Ansicht überschreiben.

Korrektur: Formularidentität und Generation schützen Navigation und Entwurf. Erfolgreiche Saves und Rollbacks lesen das maßgebliche Verbindungsregister erneut; ältere Listenantworten werden verworfen. Der neue React-Test verzögert A, öffnet B, bearbeitet B und schließt A verspätet ab.

Abschluss des Spec-Reviewers: „0 neue Spec-Befunde im Delta.“ Der A/B-Ablauf und der erhaltene B-Entwurf sind geprüft. Die zusätzliche Lock-Korrektur wurde ebenfalls gelesen.

## Unabhängig ausgeführte Nachweise

- 145 Tests der bisherigen Python-/Tk-Referenz auf Mac.
- 85 Rust-Kerntests und 2 Tauri-Bridge-Tests; Format und Clippy mit `-D warnings` bestanden.
- 22 React-Tests, Typprüfung und Produktionsbuild bestanden; npm-Audit ohne gemeldete Schwachstellen.
- Je 23 Cross-Language-/Prozessfälle auf Mac, Linux-Container und isoliert auf echtem Linux-Host bestanden.
- 23 Prüfschritte in echtem macOS-WKWebView über Rust IPC bestanden; Datenbank erhalten und beide nativen Login-Kinder beendet.
- Mac-Release lokal ad-hoc signiert, deep/strict geprüft; Debug-Testhook fehlt im Release.

Windows wurde nicht nativ ausgeführt. GitHub-CI wird durch die Zahlungs-/Ausgabenbegrenzung der Organisation vor dem Start blockiert. Produktionsaccounts und produktiver Linux-Dienst wurden nicht migriert. Vollständige Messwerte und Artefakthashes stehen in [rust-tauri-validation.json](../rust-tauri-validation.json).
