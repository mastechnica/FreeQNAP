# Contributing to FreeQNAP

The project currently has a local review candidate, not a published release. Hardware evidence is exact-model and exact-test specific. Report board/SoC revision and redacted results; never upload credentials, factory identity blocks or full flash dumps.

Keep changes small enough to audit. Storage failures must remain independent, interrupted operations must retain evidence, and the live OS must stay protected from raw disk selection. New modifying operations require explicit plans and failure tests. Do not turn missing or stale observations into success.

Run both Python suites and the source/package checks. Serial/network loopback tests are fixtures, not physical NAS acceptance. Update the capability matrix whenever behavior changes. Preserve upstream attribution and corresponding-source requirements. Publication requires owner approval in this phase.
