# Code review: claw-remote hardening

Fixed point: ce716fb20cdc8506bee448053d1994134a1d4ad4 (merged overview). Final source reviewed: 479e869. Two independent read-only reviewers ran in parallel using the code-review skill; reports were kept by axis.

## Standards

Initial P2: attaching an existing directory before registering the matching ordinary profile bypassed duplicate detection. Fixed by canonical target checks for every registration; a failing regression now passes.

Follow-up P2: restored attached Claude directories retained their old registration error. Fixed by retiring only the matching registration failure after successful validation; the restore regression also confirms unrelated provider errors remain visible.

Final reviewer: **No open findings.** Both previous P2 findings are resolved; seven focused existing-profile tests pass. No additional documented-standard violation or actionable baseline smell.

## Spec

Initial findings: Claude paths skipped validation on cached read; real-host lost-reply proof missing; timeout and leak evidence incomplete. All addressed. Actual SSH is interrupted after commit and retried safely. Native timeout asserts review state and child termination; pending queue and final native PID are checked. Missing and restored Claude path cases have regressions.

Final reviewer: **No remaining source blocker found.** All identified source/spec findings resolved at 479e869. Final package and durable evidence assembly are separately recorded in the validation report.

Standards: 0 open findings. Spec: 0 open findings. No findings were accepted without a fix.
