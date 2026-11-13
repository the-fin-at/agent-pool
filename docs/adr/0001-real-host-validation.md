# 0001: Real-host validation without credential migration

Status: accepted; generalized for portable public development.

Real-host validation uses an explicitly selected SSH connection and registered workspace supplied by the operator. No server alias, provider profile or personal account is a project default. Preserve existing SSH host-key verification and native account directories.

Run fault injection, synthetic load and upgrade scenarios in disposable pools, separate from production queues and workspaces. Existing services and credentials remain unchanged. Provider browser consent stays with the account owner; real inference requires an explicit, bounded task and must be distinguished from controlled-provider fixtures.

Store logs, measurements and screenshots in the operator's ignored `test-results/` directory or external evidence storage. Public documentation describes reproducible commands and acceptance criteria rather than personal deployment history. Use the [remote validation runbook](../remote-validation.md).
