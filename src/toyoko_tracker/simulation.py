from __future__ import annotations

import argparse
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List

from .parsing import _extract_http_offers, _extract_next_data


def toyoko_response_fixture(
    *,
    available: bool = True,
    room_count: int = 2,
    price: int = 9100,
    member_price: int = 8700,
    smoking: bool = False,
) -> str:
    vacant = max(0, int(room_count)) if available else 0
    room_name = "Smoking Single Room" if smoking else "Non-Smoking Single Room"
    payload = {
        "props": {"pageProps": {"planResponse": {
            "hotelTitle": "Toyoko Inn Simulated Hotel",
            "roomTypeList": [{
                "roomTypeName": room_name,
                "specs": {"isSmoking": bool(smoking)},
                "plans": [{
                    "planName": "Simulation Plan",
                    "price": {"generalPrice": int(price), "membershipPrice": int(member_price)},
                    "vacant": {
                        "generalVacantRoom": vacant,
                        "membershipVacantRoom": vacant,
                    },
                }],
            }],
        }}},
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{encoded}</script></body></html>'


def parse_simulated_response(html: str) -> Dict[str, Any]:
    document = _extract_next_data(html)
    if not document:
        return {"ok": False, "offers": 0, "available": None}
    plan_response = (((document.get("props") or {}).get("pageProps") or {}).get("planResponse") or {})
    offers, stats = _extract_http_offers(plan_response)
    available = any(int(offer.get("remaining_norm") or 0) > 0 for offer in offers)
    return {
        "ok": True,
        "offers": len(offers),
        "available": available,
        "had_any_offer": bool(stats.get("had_any_offer")),
    }


def run_stress_test(
    *,
    iterations: int = 200,
    concurrency: int = 4,
    scenario: str = "mixed",
) -> Dict[str, Any]:
    iterations = max(1, min(5000, int(iterations)))
    concurrency = max(1, min(32, int(concurrency)))

    def run_one(index: int) -> float:
        if scenario == "available":
            available = True
        elif scenario == "unavailable":
            available = False
        else:
            available = index % 3 == 0
        html = toyoko_response_fixture(
            available=available,
            room_count=(index % 5) + 1,
            price=8000 + (index % 12) * 250,
            smoking=index % 2 == 0,
        )
        started = time.perf_counter()
        parsed = parse_simulated_response(html)
        if not parsed["ok"]:
            raise RuntimeError("simulated response parse failed")
        return (time.perf_counter() - started) * 1000

    started = time.perf_counter()
    latencies: List[float] = []
    errors: List[str] = []
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="simulated-provider") as executor:
        futures = [executor.submit(run_one, index) for index in range(iterations)]
        for future in as_completed(futures):
            try:
                latencies.append(future.result())
            except Exception as exc:
                errors.append(str(exc))
    elapsed = max(0.000001, time.perf_counter() - started)
    ordered = sorted(latencies)
    p95_index = min(len(ordered) - 1, int(len(ordered) * 0.95)) if ordered else 0
    return {
        "ok": not errors,
        "scenario": scenario,
        "iterations": iterations,
        "concurrency": concurrency,
        "completed": len(latencies),
        "errors": len(errors),
        "error_samples": errors[:5],
        "elapsed_ms": int(round(elapsed * 1000)),
        "throughput_per_sec": round(len(latencies) / elapsed, 1),
        "average_latency_ms": round(statistics.fmean(latencies), 3) if latencies else None,
        "p95_latency_ms": round(ordered[p95_index], 3) if ordered else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Toyoko Chan response parser stress test")
    parser.add_argument("--iterations", type=int, default=500)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--scenario", choices=("mixed", "available", "unavailable"), default="mixed")
    args = parser.parse_args()
    print(json.dumps(run_stress_test(**vars(args)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
