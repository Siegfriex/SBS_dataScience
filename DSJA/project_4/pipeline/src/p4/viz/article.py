from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from p4.analysis.segmented import require_crawl_release_provenance
from p4.common.hashing import sha256_file


def build_metric_figure(
    time_series: pd.DataFrame,
    metric: str,
    output_path: str | Path,
    data_provenance: str,
) -> dict[str, object]:
    require_crawl_release_provenance(data_provenance)
    required = {"periodMonth", metric}
    if not required.issubset(time_series.columns):
        raise ValueError(f"figure input missing columns: {sorted(required - set(time_series.columns))}")
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    figure, axis = plt.subplots(figsize=(10, 5))
    axis.plot(pd.to_datetime(time_series["periodMonth"]), time_series[metric])
    axis.set(title=metric, xlabel="Month", ylabel=metric)
    axis.grid(alpha=0.25)
    figure.tight_layout()
    figure.savefig(target, dpi=160)
    plt.close(figure)
    return {"path": str(target), "metricId": metric, "sha256": sha256_file(target)}

