"""Capture public Data912 and BYMA data for a GGAL cross-source audit.

Read-only HTTP requests. Retrieval times are not market timestamps.
Run with --capture to retrieve; without it, inspect the saved evidence offline.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from byma_data import BymaData


def capture(output):
    archive = {"started_at": datetime.now(timezone.utc).isoformat(), "sources": {}}
    for name, path in {
        "arg_options": "/live/arg_options",
        "arg_stocks": "/live/arg_stocks",
        "usa_adrs": "/live/usa_adrs",
        "usa_options": "/eod/option_chain/GGAL",
        "volatilities": "/eod/volatilities/GGAL",
    }.items():
        entry = {"url": "https://data912.com" + path}
        try:
            response = requests.get(entry["url"], timeout=(10, 40))
            entry.update(status=response.status_code,
                         retrieved_at=datetime.now(timezone.utc).isoformat(),
                         headers={k: response.headers[k] for k in
                                  ("Date", "Age", "Last-Modified", "Cache-Control", "CF-Cache-Status")
                                  if k in response.headers})
            response.raise_for_status()
            entry["data"] = response.json()
        except (requests.RequestException, ValueError) as exc:
            entry["error"] = type(exc).__name__
        archive["sources"][name] = entry
        output.write_text(json.dumps(archive, indent=2), encoding="utf-8")
        print(name, entry.get("status"), "rows", len(entry.get("data", [])), flush=True)
    client = BymaData()
    try:
        for name in ("options", "leading-equity"):
            entry = {}
            try:
                entry["data"] = client.panel(name)
                entry["retrieved_at"] = datetime.now(timezone.utc).isoformat()
            except Exception as exc:
                entry["error"] = str(exc)
            archive["sources"]["byma_" + name] = entry
            output.write_text(json.dumps(archive, indent=2), encoding="utf-8")
            print("byma_" + name, "rows", len(entry.get("data", [])), entry.get("error", ""), flush=True)
    finally:
        client.close()


def inspect(path):
    archive = json.loads(path.read_text(encoding="utf-8"))
    for name, entry in archive["sources"].items():
        data = entry.get("data", [])
        print(name, {k: v for k, v in entry.items() if k != "data"})
        if isinstance(data, list):
            rows = [r for r in data if (str(r.get("symbol", "")).startswith("GFG")
                    or r.get("symbol") == "GGAL" or r.get("s_symbol") == "GGAL"
                    or r.get("underlyingSymbol") == "GGAL")]
            print("total", len(data), "GGAL", len(rows), "sample", rows[:2] or data[:1])
        else:
            print(str(data)[:1600])


def compare(path):
    archive = json.loads(path.read_text(encoding="utf-8"))
    prior = json.loads((ROOT / "research/byma_snapshot_20260907.json").read_text(encoding="utf-8"))
    current = {r["symbol"]: r for r in archive["sources"]["arg_options"]["data"]
               if r["symbol"].startswith("GFG")}
    byma = {r["symbol"]: r for r in prior["options"]
            if r.get("underlyingSymbol") == "GGAL" and r.get("denominationCcy") == "ARS"
            and str(r.get("settlementType")) == "2" and r.get("securityType") == "OPT"}
    def positive(value):
        return isinstance(value, (int, float)) and math.isfinite(value) and value > 0

    details = []
    fields = {"bid": ("px_bid", "bidPrice"), "ask": ("px_ask", "offerPrice"),
              "price_vs_trade": ("c", "trade"), "volume": ("v", "volume")}
    for symbol in sorted(current.keys() & byma.keys()):
        d, b = current[symbol], byma[symbol]
        row = {"symbol": symbol, "byma_expiration": b.get("maturityDate"),
               "data912": d, "byma": {key: b.get(key) for key in
                ("bidPrice", "offerPrice", "trade", "previousClosingPrice", "volume", "tradeHour")},
               "differences": {}}
        for name, (dk, bk) in fields.items():
            dv, bv = d.get(dk), b.get(bk)
            if positive(dv) and positive(bv):
                row["differences"][name] = {"absolute": dv-bv, "pct_of_byma": (dv/bv-1)*100}
        details.append(row)
    from statistics import median
    stats = {}
    for name in fields:
        values = [r["differences"][name] for r in details if name in r["differences"]]
        stats[name] = {"positive_pairs": len(values),
                       "equal": sum(math.isclose(v["absolute"], 0, abs_tol=1e-9) for v in values),
                       "median_absolute_pct_difference": median(abs(v["pct_of_byma"]) for v in values) if values else None}
    result = {
        "data912_retrieved_at": archive["sources"]["arg_options"]["retrieved_at"],
        "byma_archive_retrieved_at": prior["retrieved_at"],
        "limitation": "Different retrieval times; neither source supplies dated local quotes. Differences do not establish errors. Data912 settlement and contract metadata are unverified. c can retain a price when volume is zero.",
        "data912_ggal_contracts": len(current), "byma_archived_ggal_contracts": len(byma),
        "matched_symbols": len(details), "data912_only": sorted(current.keys()-byma.keys()),
        "byma_only": sorted(byma.keys()-current.keys()),
        "data912_positive_noncrossed_bid_ask": sum(positive(r.get("px_bid")) and positive(r.get("px_ask")) and r["px_ask"] >= r["px_bid"] for r in current.values()),
        "data912_positive_volume": sum(positive(r.get("v")) for r in current.values()),
        "data912_positive_c_with_zero_volume": sum(positive(r.get("c")) and r.get("v") == 0 for r in current.values()),
        "field_summary": stats, "contracts": details,
    }
    target = path.with_name("data912_comparison_20260908.json")
    target.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "contracts"}, indent=2))
    print("Archived BYMA spot", prior.get("spot"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", action="store_true")
    parser.add_argument("--compare", action="store_true", help="Compare saved local data to the September 7 BYMA archive")
    parser.add_argument("--archive", type=Path, default=ROOT / "research/data912_snapshot_20260908.json")
    args = parser.parse_args()
    if args.capture:
        capture(args.archive)
    if args.compare:
        compare(args.archive)
    else:
        inspect(args.archive)
