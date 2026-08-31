# M6_LOCAL_CANDIDATE_CLOSURE_V1.0.1

**PREPARATION_ONLY / SYNTHETIC_ONLY / LOCAL_CANDIDATE / NOT_FOR_SUBMISSION**

Candidate verdict: `ACCEPT`, pending independent audit. v1.0.1 replaces v1.0.0 after independent audit found a payload bypass. The corrected package uses an exact JSON schema with duplicate/unknown-key rejection, scans actual allowlisted payload bytes, verifies the actual M5 archive and 34 member hashes, validates a subject/object/version/hash/action/target/validity evidence-use binding, and exposes one built-in read-only action through an immutable default-deny dispatcher. It executes one positive control and 32 fail-closed adversarial cases.

This is not an ambient operating-system sandbox and does not claim control over commands invoked outside the packaged action boundary. Formal submission, public release, production, real-enterprise data, credentials, remote writes, and formal passport publication remain absent from the dispatcher and `HUMAN_REQUIRED`.
