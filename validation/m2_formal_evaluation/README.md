# M2 Formal V4 re-freeze

This portable evidence package is the non-overwriting V4 candidate requested after V3 review.

Use CPython 3.12 and verify `manifest.sha256` plus `wheelhouse-py312.sha256`. Install only from `wheelhouse-py312` using `requirements-py312.lock`, then execute the exact replay command recorded in `M2_FORMAL_REFROZEN_PATCH_AND_PYTEST_V4.md` three times.

The package contains only the accepted provider import-order patch, pytest 9.0.3, Pygments 2.20.0, frozen dependencies, raw/per-case replay logs, dependency audit evidence, and the approved sanitized audit-chain evidence. It does not contain a virtual environment, Git metadata, Truth正文, credentials, or external-model output.
