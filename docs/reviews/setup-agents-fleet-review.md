# Setup-Skills: Review und Nachweise

Quellstand: a13ea50; Fixed point: 0e4523df06cafd6c0590777fc41a2087517acdcb. Issue #9.

## Standards

Unabhängiger Reviewer: **0 offene Befunde**. Installer prüft alle Ziele vor Änderungen, installiert den Setup-Skill für beide Agenten und erhält vorhandene Anpassungen. Referenzen sind im Skill gebündelt; keine persönlichen Servernamen, Zugangsdaten oder Login-Codes eingebettet.

## Spec

Unabhängiger Reviewer: **0 offene Befunde**. Zwei realistische Anfragen wurden mit dem Skill als Handlungsgrundlage durchgespielt. Windows als reiner Remote-Client und ein Mac-Update mit eigenen Skill-Anpassungen/laufendem Remote-Auftrag ergeben ausführbare nächste Schritte. Anbieter-Zustimmung bleibt ehrlich offen. Das war eine Simulation und kein zusätzlicher Windows-Runtime-Test.

## Ausführung

- Drei Skill-Pakete bestehen `skill-creator/scripts/quick_validate.py`. Dessen PyYAML wurde in einer isolierten temporären Validierungsumgebung installiert.
- Neuer Installer-Test: vor der Änderung rot, danach grün. Fresh Install enthält Programm, beide Betriebs-Skills und den neuen Setup-Skill; erneuter Installationsversuch lehnt Überschreiben ab und erhält eigene Anpassungen.
- Komplette lokale Suite: **129 Tests bestanden**, inklusive tatsächlichem Tk. Neuer Installer-Test zusätzlich auf dem realen Linux-Host bestanden.
- Alle drei Skills in Codex-/Claude-Skill-Verzeichnisse auf Mac und `claw-remote` installiert. Bisherige Mac-Dateien entsprachen dem vorigen Repository-Stand; aktualisierte Dateien wurden gesichert. Keine Provider-Anmeldung gestartet, keine Credentials verschoben, kein Worker neu gestartet.
- Skill-Erkennung kann eine neue Agenten-Sitzung benötigen.

Standards: 0 offene Befunde. Spec: 0 offene Befunde.

## Unabhängiger Forward-Test

# Setup skill forward-test at a13ea50

Read-only simulation from `setup-agents-fleet/SKILL.md`, its bundled install/sign-in references, and repository instructions that the install reference directs the agent to read. No commands below were executed; no installation, state, login, or credential access occurred.

## A — Windows remote-only dashboard, two Codex accounts on an existing SSH Linux pool

1. Check Windows Python is 3.11+, Tk can open a window, Git is available, and OpenSSH works. Inventory existing Agent Fleet binaries, personal app, remotes and versions. Do not install local Codex or Claude: the client needs neither.
2. Resolve the chosen existing SSH alias and pool user, verify the host key through a trusted source, and use key access without agent forwarding. Inspect server CLI version, pool path, profiles, jobs, workspaces and worker before changing anything. Reuse this pool and worker.
3. Identify an authorized checkout by Git remote or clone the private repository. Read its desktop/remote instructions; compare release assets with current source and require >=0.4.1 on client/server. Preserve a dirty checkout by building separately. If the server needs upgrading, retain queue/logins and wait for running work before controlled worker restart.
4. On Windows build CLI and portable desktop with `py -3 scripts/build_zipapp.py`, `py -3 scripts/build_desktop.py --portable-only`; use the fresh installer only when destinations do not exist. Keep the portable desktop at a durable path. Launch with `pyw -3 '<durable-path>\Agent Fleet.pyzw'`.
5. Reuse or add the remote connection with exact server executable and pool path; run remote test and cached status. Add two separate Codex profiles in the selected remote view, or reuse appropriate prepared profiles. Guide the owner through each device code, explicitly selecting the intended browser account each time. Await native confirmed ChatGPT logins and refreshed account state.
6. Verify both profiles connected and enabled, worker online, and remote test/status good. A bounded read job is optional. Report exact versions/paths, profiles and any browser steps still open.

## B — Update existing Mac with custom skills and running remote work; old Linux Claude must not replace global Claude

1. Inventory Mac executable/app/skills, source state, chosen remote and active task/worker. Back up CLI/app/skills; compare custom skill text before targeted copying. Do not use the refusing fresh installer as an overwrite mechanism.
2. Build current compatible Mac CLI/app in an isolated checkout/build environment if needed. Preserve unknown app sessions, replace selected artifacts deliberately, retain local pool/remotes and custom skill edits. Verify version and actual app loading.
3. Inspect the old Linux Claude's compatibility. The sign-in reference offers a separate profile with a new name and an absolute newer native binary path; choose that route to honor the global-install constraint. Obtain the current native installation method from official Claude documentation and install to a distinct location without replacing the existing global binary. Register the separate executable with local server administration.
4. Do not stop the running remote task or worker. Defer any required Fleet worker restart until task completion and then restart only that pool's service. Leave its existing profile/session and queue intact.
5. After the selected new Claude profile is free, start its native subscription login. Owner performs browser consent and supplies any full return code through masked UI or stdin. Check `configDirectory`, `loggedIn`, successful session and connected status; unknown usage stays unknown. Verify remote worker/status after any deliberate update.

Human consent is a required remaining interaction in both scenarios. Until supplied, report “Anmeldung offen” with target/session and exact browser action; do not claim login success or poll indefinitely.
