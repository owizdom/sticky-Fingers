"""Aggregate a results file into the headline table + figures.

Usage:
    python -m sticky_fingers.analyze            # uses newest results/raw/*.jsonl
    python -m sticky_fingers.analyze --path results/raw/run_XXXX.jsonl
"""

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from .metrics import aggregate, latest_raw, load_runs  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default=None, help="path to a results .jsonl (default: newest)")
    args = ap.parse_args()

    path = args.path or latest_raw()
    if not path:
        raise SystemExit("no results found in results/raw/ -- run the experiment first")

    df = load_runs(path)
    agg = aggregate(df)

    pd.set_option("display.width", 180)
    pd.set_option("display.max_columns", 20)
    print(f"\n=== Sticky Fingers results ({os.path.basename(path)}) === runs={len(df)}\n")
    print(agg.to_string(index=False))

    os.makedirs("results", exist_ok=True)
    agg.to_csv(os.path.join("results", "summary.csv"), index=False)

    os.makedirs(os.path.join("results", "figures"), exist_ok=True)

    # Containment by architecture, per scenario (averaged over model tiers).
    cont = agg.groupby(["scenario", "arch"])["containment_rate"].mean().unstack("arch")
    ax = cont.plot(kind="bar")
    ax.set_ylabel("containment rate (attack attempts blocked)")
    ax.set_ylim(0, 1.05)
    ax.set_title("Attack containment by authorization architecture")
    ax.legend(title="architecture")
    plt.tight_layout()
    plt.savefig(os.path.join("results", "figures", "containment.png"), dpi=140)
    plt.close()

    # Attack-attempt rate by model tier, per scenario.
    att = agg.groupby(["model", "scenario"])["attempt_rate"].mean().unstack("scenario")
    ax = att.plot(kind="bar")
    ax.set_ylabel("attack-attempt rate")
    ax.set_ylim(0, 1.05)
    ax.set_title("Attack-attempt rate by model tier")
    ax.legend(title="scenario")
    plt.tight_layout()
    plt.savefig(os.path.join("results", "figures", "attempt_rate.png"), dpi=140)
    plt.close()

    print("\nsaved: results/summary.csv, results/figures/containment.png, results/figures/attempt_rate.png")


if __name__ == "__main__":
    main()
