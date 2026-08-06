"""Command-line entry point for restartable collector stages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .apq import APQClient
from .assets import build_asset_frontier, collect_pending_assets
from .config import RunConfig, locate_project_root
from .coverage import collect_month
from .detail import collect_pending_details
from .manifests import RawResponseRecorder
from .policy import PolicyHttpClient
from .query_registry import QueryRegistry
from .release import build_observed_input_package, crawl_release_readiness, recover_source_state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="p4-crawl")
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--run-id", default="E2E_20260806_RESUME_01")
    parser.add_argument("--run-mode", choices=("observed-dev", "production"), default="observed-dev")
    parser.add_argument("--crawl-release-id", default="CRAWL_20260806_03")
    parser.add_argument("--execute-live", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("recover")
    subparsers.add_parser("build-observed-input")
    subparsers.add_parser("release-readiness")
    for name in ("index", "detail", "assets"):
        stage = subparsers.add_parser(name)
        stage.add_argument("--max-items", type=int, default=0)
    return parser


def _config(args: argparse.Namespace) -> RunConfig:
    return RunConfig(
        project_root=(args.project_root or locate_project_root()),
        run_id=args.run_id,
        run_mode=args.run_mode,
        phase=args.command,
        crawl_release_id=args.crawl_release_id,
        execute_live=args.execute_live,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = _config(args)
    if args.command == "recover":
        result = recover_source_state(config)
    elif args.command == "build-observed-input":
        result = build_observed_input_package(config)
    elif args.command == "release-readiness":
        result = crawl_release_readiness(config)
    else:
        config.require_live()
        config.ensure_run_layout()
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("Live collection requires the project environment with httpx") from exc
        native = httpx.Client(
            headers={
                "User-Agent": "P4-A1-SOURCE/1.0 non-commercial-research",
                "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
                "Referer": "https://linkareer.com/",
            },
            follow_redirects=True,
            timeout=httpx.Timeout(30.0, connect=15.0),
        )
        fetch_manifest = config.run_root / "manifests" / f"{args.command}_fetch_manifest.jsonl"
        recorder = RawResponseRecorder(config.crawl_root, config.run_id, fetch_manifest)
        http = PolicyHttpClient(native.get, minimum_interval=1.0, concurrency=2, response_hook=recorder)
        try:
            if args.command == "index":
                state = recover_source_state(config)
                remaining = pd.read_csv(config.run_root / "state" / "remaining_months.csv", encoding="utf-8-sig")
                periods = remaining["periodMonth"].astype(str).tolist()
                if args.max_items > 0:
                    periods = periods[: args.max_items]
                apq = APQClient(http, QueryRegistry.load(config.crawl_root / "configs" / "queryRegistry.yaml"))
                rows = [collect_month(period, apq, config.run_root / "coverage") for period in periods]
                result = {"recovered": state, "monthsAttempted": len(rows), "coverage": rows}
            elif args.command == "detail":
                recover_source_state(config)
                frontier_path = config.run_root / "state" / "detail_frontier.parquet"
                frontier = pd.read_parquet(frontier_path)
                updated = collect_pending_details(frontier, http, config.run_root / "state", max_items=args.max_items)
                result = {"rows": len(updated), "states": updated["status"].value_counts().to_dict()}
            else:
                posting_path = config.run_root / "state" / "posting_manifest.parquet"
                posting = pd.read_parquet(posting_path if posting_path.exists() else config.release_root / "posting_manifest.parquet")
                frontier = build_asset_frontier(posting)
                rows = collect_pending_assets(
                    frontier,
                    http,
                    config.run_root / "manifests" / "asset_manifest.jsonl",
                    max_items=args.max_items,
                )
                result = {"eligibleAssets": len(frontier), "attemptedAssets": len(rows)}
        finally:
            native.close()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
