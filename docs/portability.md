# Source portability

Every distributable file and folder is included in `scripts/check_portability.py`: source, tests, scripts, hidden configuration, locks, documentation, skills, website and binary assets. Public product/provider names, package identifiers, compatibility data directories and upstream copyright notices are intentional. Host aliases and account names in examples are replaceable examples, never personal defaults.

```sh
python3 scripts/check_portability.py --report test-results/portability.json
```

The JSON report lists every reviewed path, parent directory, size, text/binary classification and content hash. The gate rejects known machine/owner identifiers in file names and text, non-example personal paths/email addresses/IPs, broken local documentation links and unreviewed/changed binary assets. Known identifier fingerprints are stored as hashes so the check does not itself republish the removed names. Original license notices retain their required attribution.

The binary registry in `scripts/portability-assets.json` binds each asset to a SHA-256 and purpose. Review new images visually and inspect their metadata/text before declaring them; fonts and icons retain upstream licenses. Updating the registry is a review step, not a way to dismiss a failing check.

## Repeatable release loop

1. Review the complete inventory and any changed path, including hidden files and images. Keep provider/brand identity distinct from machine-specific configuration.
2. Supply host, profile, artifact and workspace choices as parameters or derive paths from the current user/platform. Use reserved example domains and generic sample users.
3. Keep deployment diaries, per-run screenshots, account telemetry and live validation logs in ignored `test-results/` or external evidence storage. Public docs contain reproducible instructions and support limits.
4. Run the gate, its regression tests and the relevant [validation commands](validation.md). Fix findings and repeat. A green pattern check alone cannot prove an installer works.
5. Test the installation in a fresh isolated home and inspect the resulting distribution. Native platform, real-provider and signing gates require their own evidence.

The `Source portability` workflow repeats the gate on pushes and pull requests and uploads the per-file inventory. This checks the current source tree, not historical commits, other branches, GitHub discussions or installed user state. It is a portability guard, not a general secret scanner or a replacement for code review.
