from __future__ import annotations

from pathlib import Path

from crawl.control.notebook_bundle import dependency_order_audit, notebook_plan


PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_current_plan_is_topological() -> None:
    plan = notebook_plan(PROJECT_ROOT)
    rows = dependency_order_audit(PROJECT_ROOT, plan)
    assert rows
    assert all(row["status"] == "PASS" for row in rows)


def test_ncs_consumers_follow_agent4_producers() -> None:
    stage_ids = [stage_id for _, stage_id, _ in notebook_plan(PROJECT_ROOT)]
    positions = {stage_id: index for index, stage_id in enumerate(stage_ids)}
    assert positions["A4-00-NCS-SOURCE"] < positions["A2-08-NCS-LOAD"]
    assert positions["A4-01-CODESET"] < positions["A2-08-NCS-LOAD"]
    assert positions["A4-03-MAP-OBSERVED"] < positions["A2-09-NCS-MAP"]
    assert positions["A4-04-EXPORT"] < positions["A2-09-NCS-MAP"]
    assert positions["A2-09-NCS-MAP"] < positions["A2-10-EXPORT"]


def test_master_is_last_when_included() -> None:
    plan = notebook_plan(PROJECT_ROOT, include_master=True)
    assert plan[-1][1] == "A3-MASTER"
