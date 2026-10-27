# Execution decisions and verification

Measured 27 October 2026. Implementation used one native executor and one fresh whole-branch reviewer, followed by one regression-tested fix pass. Seven Important findings were fixed; there are no deferred minors. The full post-fix suite passed 95 Python tests and nine Node tests. The upstream SDK's known beta/deprecation warnings remain visible.

## Rulings and practical limits

| Decision | Reason | Consequence if the assumption is wrong |
| --- | --- | --- |
| Use existing WSL Docker with native Windows Python/Node | No system installation needed | Mount/localhost differences; actual container and cross-platform build checks passed |
| Pass frozen GateInput to decision persistence | Normalized audit links and digest verification need actual inputs | A linkage error would invalidate the audit; repository checks bind inputs to records |
| Add a qualification API/CLI operation | Saved human-review packets need a scoring operation | Additional local API surface; paid execution remains unavailable |
| Leave actual human/live/paid acceptance pending | Outside the offline authorization | Treating scripts as real evidence would overstate model quality |
| Leave hosted account/transfer acceptance pending | No hosted destination approved | Hosted success cannot yet be claimed |
| Leave hosted CI unobserved | Repository has not been published | Local checks do not establish a hosted run |
| Exclude enterprise auth/HA/SLAs/backup operations | Bounded loopback demonstration | No production-readiness claim follows |
| Bind inputs with hashes without asserting independent authenticity | Local owner controls evidence | These records are not third-party attestations |
| Use checkout execution and frozen v1 policy | Only the documented execution convention is supported | Arbitrary working directories/general policies are not promised |
| Treat study IDs as a workflow boundary | Local owner is trusted | A new ID cannot make reused holdout evidence untouched |
| Keep mixed semantic negative/abstention inconclusive | Only exact violations have unconditional override | Some releases remain blocked pending usable judgments |

## Evidence retained

Current and historical scripted captures, dataset and rubric/policy files are retained in Git. Original pre-fix requests were not reconstructed; corrected samples use new capture identities. Actual human label count is zero; scripted label count per demo is 24. Provider call count and spend are zero. Hosted tracing synchronization was tested only with offline destinations, including actual SDK sampling behavior.

The local process demonstration observed accept/reject/reject/inconclusive and CLI exits 0/1/1/2. PostgreSQL tests use fresh disposable schemas, immutable decision dependencies and restart readback. Actual container import/readback and API restart checks passed using a non-root process and fresh artifact/database volumes. Named volumes retain evidence when containers stop.
