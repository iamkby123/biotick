"""Stress test biotick-api.fly.dev.

Ramps concurrency 5 -> 100, hits a realistic endpoint mix, reports p50/p95/p99
and error rate. Stops early if the server starts returning 5xx or timing out.
"""

import asyncio
import random
import statistics
import time
from collections import Counter

import httpx

BASE = "https://biotick-api.fly.dev/api"

# Top biotech tickers most likely to be visited
TICKERS = [
    "MRNA", "PFE", "VRTX", "BNTX", "REGN", "GILD", "BMY", "LLY", "MRK", "JNJ",
    "ABBV", "AMGN", "BIIB", "ILMN", "INCY", "NVS", "AZN", "GSK", "NVO",
]

# Real NCT ids from the DB (pulled at startup)
NCT_POOL: list[str] = []

# (name, weight, path_fn) — weights roughly mirror real traffic patterns
def build_scenarios():
    return [
        ("list",         30, lambda: f"/companies?page={random.randint(1,5)}&per_page=25"),
        ("detail",       20, lambda: f"/companies/{random.choice(TICKERS)}"),
        ("catalysts",    15, lambda: "/catalysts"),
        ("earnings",     10, lambda: "/earnings?start=2026-04-18&end=2026-05-18"),
        # Batch endpoint exercises the same code path even with unknown NCTs (returns empty map + 200).
        ("pred_batch",   10, lambda: f"/predictions/batch?ids={','.join(random.sample(NCT_POOL, min(8, len(NCT_POOL))))}" if NCT_POOL else "/predictions/batch?ids=NCT00000001,NCT00000002,NCT00000003"),
        ("pdufa",         5, lambda: "/pdufa"),
        ("health",        5, lambda: "/health"),
        ("historical",    5, lambda: "/historical/catalysts?per_page=25"),
    ]


async def fetch_nct_pool(client):
    """Grab a handful of real NCT ids so the batch-predictions test is realistic."""
    try:
        # MRNA has plenty of trials
        r = await client.get(f"{BASE}/companies/MRNA", timeout=20)
        if r.status_code == 200:
            data = r.json()
            NCT_POOL.extend(t["nct_id"] for t in data.get("trials", [])[:15])
        r = await client.get(f"{BASE}/companies/VRTX", timeout=20)
        if r.status_code == 200:
            data = r.json()
            NCT_POOL.extend(t["nct_id"] for t in data.get("trials", [])[:15])
    except Exception as e:
        print(f"  (nct pool seed failed: {e})")
    print(f"  Seeded {len(NCT_POOL)} real NCT ids for batch tests")


async def worker(client, requests_per_worker, results, scenarios):
    weights = [s[1] for s in scenarios]
    for _ in range(requests_per_worker):
        name, _, path_fn = random.choices(scenarios, weights=weights)[0]
        path = path_fn()
        t0 = time.perf_counter()
        try:
            r = await client.get(f"{BASE}{path}", timeout=30)
            dt = (time.perf_counter() - t0) * 1000
            results.append((name, r.status_code, dt, None))
        except Exception as e:
            dt = (time.perf_counter() - t0) * 1000
            results.append((name, 0, dt, type(e).__name__))


def stats(values):
    if not values:
        return {}
    values = sorted(values)
    n = len(values)
    def pct(p): return values[min(int(n * p / 100), n - 1)]
    return {"p50": pct(50), "p95": pct(95), "p99": pct(99), "max": values[-1], "min": values[0]}


async def run_test(concurrency, total_requests, scenarios):
    print(f"\n=== concurrency={concurrency}, total={total_requests} ===")
    per_worker = max(1, total_requests // concurrency)
    actual_total = per_worker * concurrency
    results = []

    start = time.perf_counter()
    # Keep-alive connection pool shared across workers
    limits = httpx.Limits(max_connections=concurrency * 2, max_keepalive_connections=concurrency)
    async with httpx.AsyncClient(limits=limits) as client:
        tasks = [worker(client, per_worker, results, scenarios) for _ in range(concurrency)]
        await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    # Overall stats. For capacity planning only count 5xx + network errors as
    # failures; 4xx is the server working correctly on bad input.
    times_ok = [r[2] for r in results if 200 <= r[1] < 400]
    statuses = Counter(r[1] for r in results)
    errors = [r for r in results if r[1] == 0 or r[1] >= 500]
    four_xx = [r for r in results if 400 <= r[1] < 500]

    s = stats(times_ok)
    print(f"  duration:   {elapsed:.1f}s")
    print(f"  throughput: {len(results)/elapsed:.1f} req/s")
    if s:
        print(f"  latency:    p50 {s['p50']:>5.0f}ms   p95 {s['p95']:>5.0f}ms   p99 {s['p99']:>5.0f}ms   max {s['max']:>5.0f}ms")
    print(f"  statuses:   {dict(statuses)}")
    if four_xx:
        print(f"  4xx:        {len(four_xx)} (expected for unknown tickers; not a capacity failure)")
    if errors:
        err_types = Counter(r[3] or f"HTTP{r[1]}" for r in errors)
        print(f"  FAILURES:   {len(errors)/len(results)*100:.1f}% ({len(errors)}/{len(results)})")
        for e, n in err_types.most_common(3):
            print(f"              {n}x {e}")

    # Per-endpoint p95
    by_name = {}
    for r in results:
        by_name.setdefault(r[0], []).append((r[1], r[2]))
    print("  per endpoint:")
    for name, rows in sorted(by_name.items()):
        oks = [t for st, t in rows if 200 <= st < 400]
        errs = len(rows) - len(oks)
        s2 = stats(oks)
        if s2:
            print(f"    {name:<12} n={len(rows):>4}  p50 {s2['p50']:>5.0f}ms  p95 {s2['p95']:>5.0f}ms  err {errs}")
        else:
            print(f"    {name:<12} n={len(rows):>4}  ALL FAILED")

    return statuses, len(errors), len(results)


async def main():
    print("Pre-flight")
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE}/health", timeout=10)
        print(f"  Health: {r.status_code} ({r.elapsed.total_seconds()*1000:.0f}ms)")
        if r.status_code != 200:
            print("  Aborting — backend not healthy")
            return
        await fetch_nct_pool(client)

    scenarios = build_scenarios()

    # Ramp. Stop if error rate > 5% at any level.
    levels = [
        (5,   50),
        (20,  200),
        (50,  500),
        (100, 1000),
    ]
    for concurrency, total in levels:
        statuses, errors, total_done = await run_test(concurrency, total, scenarios)
        err_rate = errors / total_done if total_done else 1
        if err_rate > 0.05:
            print(f"\nBacking off — error rate {err_rate*100:.1f}% exceeds 5%")
            break
        # Let the machine breathe between rounds
        await asyncio.sleep(5)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
