# Session retrospective

Primary sources: native archive failures on the actual server, the red/green test outputs, two-axis review, and the recorded user/fault/performance runs.

The main environment gap was source-only subprocess verification. The new installed-archive test builds the real distributable, runs it outside the source tree under its extensionless install name, and checks both detached login and exit codes 0/1/2. It runs with the existing unittest CI command; a second overlapping guardrail is unnecessary.

The three opt-in real-host runners now distinguish actual inference, actual SSH, controlled native processes, and injected network delay. Their evidence stays under one runbook and one JSON report. Use unique output filenames per simultaneous harness run to prevent competing writers.

Remaining environment blocker: GitHub Actions billing/spending prevents hosted jobs from starting. Repair account billing outside this code change before relying on hosted matrix checks. Native Windows GUI acceptance still needs a Windows machine.
