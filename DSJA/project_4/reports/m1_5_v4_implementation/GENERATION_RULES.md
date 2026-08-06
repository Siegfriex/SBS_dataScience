# P4 M1.5 v4.0 control artifact generation rules

`integration/SEMANTIC_STAGE_REGISTRY.yaml` is the machine-authoritative stage registry.
`P4_M1_5_STAGE_REGISTRY.yaml` is a synchronized report copy and must remain byte-identical.

Generation rule:

```bash
cp integration/SEMANTIC_STAGE_REGISTRY.yaml \
  reports/m1_5_v4_implementation/P4_M1_5_STAGE_REGISTRY.yaml
python integration/validate_m1_5_control.py
```

The validator fails closed when the two files differ, a schema is missing or invalid,
a status falls outside the seven-value vocabulary, a gate references an unknown stage,
or the dependency graph is missing, inconsistent, or cyclic.

Runtime evaluation precedence is fixed:

1. registry/validator error -> `FAIL`
2. known dependency outside `PASS|PASS_WITH_FINDINGS` -> `BLOCKED`
3. zero evidence after dependencies pass -> `NOT_EVALUATED`
4. otherwise retain the explicitly evaluated allowed status

`NOT_STARTED` is stage scheduling state. It is not evidence of gate evaluation.
