# Agent Fleet engineering

## Agent skills

Issues and specs use GitHub: see `docs/agents/issue-tracker.md`. Triage roles use `docs/agents/triage-labels.md`. Read `GLOSSARY.md` and relevant `docs/adr/` decisions before domain changes; layout rules are in `docs/agents/domain.md`.

For source changes, run `python3 scripts/check_portability.py` and the checks in `docs/validation.md` relevant to the change. Every distributable file and folder is in scope, including documentation, test fixtures and assets. Use generic example identities and parameterized host/path inputs. Put machine-specific reports under ignored `test-results/` and keep real-host acceptance separate from controlled fixtures. For opt-in host verification, use `docs/remote-validation.md` with an explicitly selected target.
