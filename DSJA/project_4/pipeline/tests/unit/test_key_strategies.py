import pytest
import yaml
from pathlib import Path

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


def test_strategy_loads_exact_v212_key_contract():
    contract_path = Path(__file__).resolve().parents[3] / "shared/contracts/P4_CONTRACT_v2.1.2/p4_contract.yaml"
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    strategy = CanonicalContractStrategy.from_contract(contract)
    assert strategy.make("postingId", "linkareer", "123") == "PST_8a245070a5ece697d6cf"
    assert strategy.make("rawPostingId", "linkareer", "123", "a" * 64) == "RAW_1ffe6e05045f37a6271f"
    assert strategy.make("trackId", "PST_demo", 0) == "TRK_7bcc98532a391ab10796"
