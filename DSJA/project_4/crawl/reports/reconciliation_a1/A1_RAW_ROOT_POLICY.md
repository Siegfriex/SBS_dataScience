# A1 External Raw Root Policy

- branch: `agent/p4-a1-reconcile-crawl-authority-v1`
- baseCommit: `5508fce02ba5396b5d5a55870f1f879c1f32e8e0`
- headCommit: `92207e8fe7cc445c7426218da06b0b064f9df941`
- dataVersion: `observed-dev-reconciliation-20260807.1`
- runId: `A1_RECON_20260807_01`
- rawStorageRootId: `P4_RAW_OBSERVED_20260806_01`
- mountPolicyVersion: `p4-raw-mount-v1`

Raw bytes are immutable external objects and are not Git authority. Consumers map the
storage root ID at runtime, resolve only `objectLocatorRelative`, and verify compressed
SHA-256, decompressed content SHA-256, and byte counts. An unmounted root, missing object,
or mismatch fails closed. There is no fixture or zero-row fallback and no release promotion.
