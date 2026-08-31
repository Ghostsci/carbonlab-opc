# Rebuild

Run `./scripts/replay_g1_b_v2.sh /absolute/empty/output/path`. The command verifies the source package, copies only the four static bootstrap files, rebuilds every deterministic output, verifies 39/39 scenarios and 51/51 controlled hashes, and exits 0. Omit the path to use a new temporary directory.

The replay must not be used to overwrite a human-approved freeze. Any changed generator, seed, rules, or file bytes requires a new version.
