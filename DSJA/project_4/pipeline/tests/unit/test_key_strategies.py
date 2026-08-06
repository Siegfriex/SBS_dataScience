import pytest

from p4.common.key_strategies import (
    CanonicalContractStrategy,
    Sha1LegacyStrategy,
    build_migration_map,
)


def canonical():
    return CanonicalContractStrategy(
        contract_version="2.1.2",
        key_contract={
            "algorithm": "sha256",
            "rules": {
                "postingId": {"prefix": "pst_", "length": 20},
                "metricId": {"prefix": "met_", "length": 24},
            },
        },
    )


def test_legacy_and_contract_keys_are_idempotent_and_versioned():
    legacy = Sha1LegacyStrategy()
    current = canonical()
    assert legacy.make("postingId", "linkareer", "123") == legacy.make("postingId", "linkareer", "123")
    assert legacy.make("postingId", "linkareer", "123").startswith("lk_")
    assert len(legacy.make("postingId", "linkareer", "123")) == 19
    assert current.make("postingId", "linkareer", "123").startswith("pst_")
    assert len(current.make("postingId", "linkareer", "123")) == 24
    assert current.contract_version == "2.1.2"


def test_canonical_strategy_refuses_missing_contract_rules():
    with pytest.raises(ValueError):
        CanonicalContractStrategy("2.1.2", {})
    with pytest.raises(KeyError):
        canonical().make("trackId", "P1", 0)


def test_migration_map_is_explicit_and_collision_checked():
    rows = build_migration_map(
        "postingId",
        [("linkareer", "1"), ("linkareer", "2")],
        Sha1LegacyStrategy(),
        canonical(),
    )
    assert len(rows) == 2
    assert rows[0]["legacyKey"] != rows[0]["canonicalKey"]
    assert rows[0]["contractVersion"] == "2.1.2"


def test_collision_sample_fails_closed():
    colliding = CanonicalContractStrategy(
        "2.1.2",
        {"algorithm": "sha256", "rules": {"postingId": {"prefix": "", "length": 0}}},
    )
    with pytest.raises(ValueError, match="collision"):
        build_migration_map(
            "postingId",
            [("linkareer", "1"), ("linkareer", "2")],
            Sha1LegacyStrategy(),
            colliding,
        )

