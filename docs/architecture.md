# Architecture

The Node adapter executes a pinned reconciliation workflow in a fresh temporary SQLite store. It exports model requests/replies, tool observations, review events, final outcomes and immutable source versions before cleanup. The original subject checkout and its historical reports/budget are untouched.

Python imports hash-bound bundles, checks exact facts and actions, calibrates a narrow explanation judge and records version decisions in PostgreSQL. Complete transcripts live in the artifact directory; PostgreSQL stores identities, scores, labels and decision references. LangSmith is an inspection surface rather than the release authority.

All current model replies are authored scripts. Fault controls preserve the original bundle digest and are explicitly injected observations, not naturally occurring subject failures. Their outputs cannot establish live model quality.
