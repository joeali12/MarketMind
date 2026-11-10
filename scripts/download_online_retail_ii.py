#!/usr/bin/env python3
"""Download Online Retail II into data/raw/ with provenance notes.

Primary URL (classic UCI ML databases path):
  https://archive.ics.uci.edu/ml/machine-learning-databases/00502/online_retail_II.xlsx

Does not commit the file. Prints SHA-256 after download.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUT = PROJECT_ROOT / "data" / "raw" / "online_retail_II.xlsx"
URL = (
    "https://archive.ics.uci.edu/ml/machine-learning-databases/"
    "00502/online_retail_II.xlsx"
)
DOI = "https://doi.org/10.24432/C5CG6D"
CITATION = (
    "Chen, D. (2012). Online Retail II [Dataset]. "
    "UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D."
)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        digest = sha256(OUT)
        print(f"Already present: {OUT} ({OUT.stat().st_size} bytes)")
        print(f"SHA-256: {digest}")
        print(f"Source DOI: {DOI}")
        print(CITATION)
        return 0

    print(f"Downloading {URL}")
    req = urllib.request.Request(URL, headers={"User-Agent": "MarketMind/0.1"})
    with urllib.request.urlopen(req, timeout=600) as resp, OUT.open("wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f.write(chunk)

    digest = sha256(OUT)
    print(f"Saved: {OUT} ({OUT.stat().st_size} bytes)")
    print(f"SHA-256: {digest}")
    print(f"Source DOI: {DOI}")
    print(CITATION)
    return 0


if __name__ == "__main__":
    sys.exit(main())
