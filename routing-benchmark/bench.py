#!/usr/bin/env python3
"""Model-routing benchmark against Crusoe Intelligence Foundry (Serverless Inference).

Sends SYNTHETIC support-triage cases (cases.py) to a small and a large model
with one fixed JSON prompt, scores priority / product area / escalate-to team,
records latency and token usage, converts tokens to cost with the per-million
prices published by the /v1/models endpoint, and then simulates routing.

Usage:
    export CRUSOE_API_KEY=...           # never printed or written by this script
    python bench.py                      # runs for real, writes results.json + results.md
    python bench.py --dry-run            # no API calls, prints the plan only

Only the standard library is required.
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from cases import AREAS, CASES, TEAMS

BASE_URL = os.environ.get("CRUSOE_BASE_URL", "https://api.inference.crusoecloud.com/v1")
SMALL_MODEL = "nvidia/Nemotron-3.5-Lightning-30B-A3B"
LARGE_MODEL = "zai-org/GLM-5.3"
MAX_TOKENS = 1500          # reasoning models spend tokens thinking; 256 caused empty replies
REASONING_EFFORT = "low"   # same setting for both models
MAX_RETRIES = 4
PRICING_PAGE = "https://www.crusoe.ai/cloud/pricing"
CONF_THRESHOLD = 3         # heuristic router: small model confidence <= this goes to large
HERE = Path(__file__).resolve().parent

SYSTEM_PROMPT = f"""You are a support triage assistant for a GPU cloud and AI inference provider.
Read the ticket and answer with ONE JSON object and nothing else:
{{"priority": "P1|P2|P3|P4", "area": "<area>", "team": "<team>", "confidence": <1-5>}}

Priority (impact x urgency):
- P1: customer production is fully down, or data loss / security exposure, happening now, no workaround.
- P2: production degraded or critical work blocked with no adequate workaround, or a hard deadline within 24 hours.
- P3: non-production, or production with a working workaround, and no near deadline.
- P4: question, how-to or clarification with no operational impact.

area, one of: {", ".join(AREAS)}
(networking includes load balancers and InfiniBand; billing_quota includes quota limits and invoices.)

team, one of: {", ".join(TEAMS)}
- compute_oncall: VM / GPU hardware and boot problems
- network_eng: load balancer, VPC, InfiniBand fabric
- storage_eng: disks and object storage
- cmk_eng: managed Kubernetes
- inference_eng: Serverless Inference platform faults
- ml_platform_eng: fine-tuning pipeline faults
- billing_quota_ops: invoices, unexpected charges, quota changes
- security_oncall: credential leaks, abuse
- support_tier1: answerable from documented behavior or customer-side fixes, no engineering escalation

confidence: 1 = guessing, 5 = certain."""


# ---- named failure classes -------------------------------------------------
class FoundryError(Exception):
    name = "FoundryError"

    def __init__(self, detail=""):
        super().__init__(f"[{self.name}] {self.message} {detail}".strip())


class FoundryKeyMissing(FoundryError):
    name = "FoundryKeyMissing"
    message = "CRUSOE_API_KEY is not set. Create an Intelligence API key in Intelligence Foundry > Inference and export it."


class FoundryAuthFailed(FoundryError):
    name = "FoundryAuthFailed"
    message = "The API rejected the key (HTTP 401/403). The key is missing, expired or revoked."


class FoundryRateLimited(FoundryError):
    name = "FoundryRateLimited"
    message = "HTTP 429 persisted after retries with backoff; the project is over its RPM/TPM limit."


class FoundryServerBusy(FoundryError):
    name = "FoundryServerBusy"
    message = "HTTP 5xx persisted after retries; the shared endpoint is busy or unavailable."


class FoundryRequestRejected(FoundryError):
    name = "FoundryRequestRejected"
    message = "The API rejected the request (HTTP 4xx other than 401/403/429), e.g. unknown model or bad parameter."


class FoundryNetworkError(FoundryError):
    name = "FoundryNetworkError"
    message = "The request did not complete (timeout or connection error)."


class EmptyCompletion(FoundryError):
    name = "EmptyCompletion"
    message = "HTTP 200 but the message content was empty (often reasoning consumed max_tokens)."


class UnparseableTriage(FoundryError):
    name = "UnparseableTriage"
    message = "The reply was not a JSON object with valid priority/area/team values."


# ---- API ---------------------------------------------------------------------
def _request(path, body=None, timeout=90):
    key = os.environ.get("CRUSOE_API_KEY")
    if not key:
        raise FoundryKeyMissing()
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE_URL + path, data=data,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "User-Agent": "crusoe-routing-bench/1.0"})
    backoff = 2.0
    last = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            code = e.code
            if code in (401, 403):
                raise FoundryAuthFailed(f"(HTTP {code})")
            if code == 429 or code >= 500:
                last = FoundryRateLimited if code == 429 else FoundryServerBusy
                retry_after = e.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.replace(".", "").isdigit() else backoff
                if attempt < MAX_RETRIES:
                    time.sleep(min(wait, 30))
                    backoff *= 2
                    continue
                raise last(f"(HTTP {code}, {MAX_RETRIES} retries)")
            raise FoundryRequestRejected(f"(HTTP {code})")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = FoundryNetworkError
            if attempt < MAX_RETRIES:
                time.sleep(backoff)
                backoff *= 2
                continue
            raise FoundryNetworkError(type(e).__name__)
    raise last()


def list_prices():
    """Per-million-token prices as published by GET /v1/models."""
    out = {}
    for m in _request("/models")["data"]:
        p = m.get("pricing") or {}
        if "prompt" in p and "completion" in p:
            out[m["id"]] = {"input": float(p["prompt"]), "output": float(p["completion"])}
    return out


def parse_triage(text):
    if not text or not text.strip():
        raise EmptyCompletion()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise UnparseableTriage("(no JSON object found)")
    try:
        d = json.loads(m.group(0))
        pr, area, team = str(d["priority"]).upper(), d["area"], d["team"]
    except (ValueError, KeyError):
        raise UnparseableTriage("(invalid JSON or missing field)")
    if pr not in ("P1", "P2", "P3", "P4") or area not in AREAS or team not in TEAMS:
        raise UnparseableTriage("(value outside the allowed labels)")
    try:
        conf = int(d.get("confidence", 0))
    except (TypeError, ValueError):
        conf = 0
    return {"priority": pr, "area": area, "team": team, "confidence": conf}


def run_case(model, ticket):
    body = {"model": model, "temperature": 0, "max_tokens": MAX_TOKENS,
            "reasoning_effort": REASONING_EFFORT,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": "Ticket:\n" + ticket}]}
    t0 = time.time()
    rec = {"latency_s": None, "prompt_tokens": 0, "completion_tokens": 0,
           "prediction": None, "failure": None, "message": None}
    try:
        resp = _request("/chat/completions", body)
        rec["latency_s"] = round(time.time() - t0, 3)
        u = resp.get("usage") or {}
        rec["prompt_tokens"] = u.get("prompt_tokens", 0)
        rec["completion_tokens"] = u.get("completion_tokens", 0)
        rec["finish_reason"] = resp["choices"][0].get("finish_reason")
        rec["prediction"] = parse_triage(resp["choices"][0]["message"].get("content"))
    except FoundryKeyMissing:
        raise
    except FoundryAuthFailed:
        raise
    except FoundryError as e:
        rec["latency_s"] = rec["latency_s"] or round(time.time() - t0, 3)
        rec["failure"], rec["message"] = e.name, str(e)
    return rec


# ---- scoring -------------------------------------------------------------------
FIELDS = [("priority", "priority"), ("area", "area"), ("team", "team")]


def score(pred, case):
    """A failed call scores 0 on every field (it did not produce a triage)."""
    if not pred:
        return {"priority": 0, "area": 0, "team": 0, "all": 0, "priority_within1": 0}
    s = {f: int(pred[f] == case[f]) for f, _ in FIELDS}
    s["all"] = int(all(s.values()))
    s["priority_within1"] = int(abs(int(pred["priority"][1]) - int(case["priority"][1])) <= 1)
    return s


def cost(rec, price):
    return (rec["prompt_tokens"] * price["input"] + rec["completion_tokens"] * price["output"]) / 1e6


def summarize(rows, label):
    n = len(rows)
    agg = {"strategy": label, "n": n}
    for k in ("priority", "area", "team", "all", "priority_within1"):
        agg["acc_" + k] = round(sum(r["score"][k] for r in rows) / n, 4)
    agg["failures"] = sum(1 for r in rows if r["failure"])
    agg["avg_latency_s"] = round(statistics.mean(r["latency_s"] for r in rows), 3)
    agg["total_cost_usd"] = round(sum(r["cost"] for r in rows), 6)
    agg["cost_per_ticket_usd"] = round(agg["total_cost_usd"] / n, 6)
    agg["large_calls"] = sum(r.get("used", "") == "large" for r in rows)
    return agg


def route(per_case, small_key, large_key, decide):
    """decide(case_row) -> True when the large model should handle it.
    A routed ticket pays for every model it touched (heuristic routes pay for the
    small attempt too); latency adds up in the same way."""
    rows = []
    for c in per_case:
        s, l = c[small_key], c[large_key]
        if decide(c):
            tot_cost = l["cost"] + (s["cost"] if c.get("_small_first") else 0)
            lat = l["latency_s"] + (s["latency_s"] if c.get("_small_first") else 0)
            src = l
            used = "large"
        else:
            tot_cost, lat, src, used = s["cost"], s["latency_s"], s, "small"
        rows.append({"score": src["score"], "failure": src["failure"], "cost": tot_cost,
                     "latency_s": lat, "used": used})
    return rows


def main():
    global MAX_TOKENS, REASONING_EFFORT
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(HERE), help="output directory")
    ap.add_argument("--max-tokens", type=int, default=MAX_TOKENS)
    ap.add_argument("--reasoning-effort", default=REASONING_EFFORT,
                    help="sent to both models; use 'none' to switch thinking off")
    ap.add_argument("--tag", default="", help="suffix for result file names, e.g. run2")
    args = ap.parse_args()
    MAX_TOKENS, REASONING_EFFORT = args.max_tokens, args.reasoning_effort
    out = Path(args.out)
    sfx = f"_{args.tag}" if args.tag else ""

    if args.dry_run:
        print(f"{len(CASES)} synthetic cases x 2 models; small={SMALL_MODEL} large={LARGE_MODEL}; max_tokens={MAX_TOKENS}")
        return 0
    try:
        prices = list_prices()
        price = {"small": prices[SMALL_MODEL], "large": prices[LARGE_MODEL]}
    except KeyError as e:
        print(f"[ModelPriceMissing] {e} is not in /v1/models pricing; cannot compute cost.")
        return 2
    except FoundryError as e:
        print(e)
        return 1

    started = datetime.now().astimezone()
    per_case = []
    try:
        for i, (diff, ticket, pr, area, team) in enumerate(CASES, 1):
            case = {"priority": pr, "area": area, "team": team}
            row = {"id": i, "difficulty": diff, "synthetic": True, "ticket": ticket, "expected": case}
            for tag, model in (("small", SMALL_MODEL), ("large", LARGE_MODEL)):
                rec = run_case(model, ticket)
                rec["score"] = score(rec["prediction"], case)
                rec["cost"] = round(cost(rec, price[tag]), 8)
                row[tag] = rec
                st = rec["failure"] or "ok"
                print(f"case {i:2d} {diff:4s} {tag:5s} {st:18s} {rec['latency_s']}s tok {rec['prompt_tokens']}+{rec['completion_tokens']}")
            per_case.append(row)
    except FoundryError as e:
        print(e)
        return 1

    for c in per_case:
        c["_small_first"] = True
    strategies = [
        summarize(route(per_case, "small", "small", lambda c: False), "small-only"),
        summarize(route(per_case, "large", "large", lambda c: False), "large-only"),
        summarize(route(per_case, "small", "large", lambda c: c["difficulty"] == "hard"), "routed: oracle (easy->small, hard->large)"),
        summarize(route(per_case, "small", "large",
                        lambda c: bool(c["small"]["failure"]) or c["small"]["prediction"]["confidence"] <= CONF_THRESHOLD),
                  f"routed: heuristic (small first; escalate on failure or confidence<={CONF_THRESHOLD})"),
        summarize(route(per_case, "small", "large",
                        lambda c: bool(c["small"]["failure"]) or c["small"]["prediction"]["priority"] in ("P1", "P2")),
                  "routed: heuristic (small first; escalate if small says P1/P2 or fails)"),
    ]
    for c in per_case:
        c.pop("_small_first")
        for t in ("small", "large"):
            c[t]["finish_reason"] = c[t].get("finish_reason")
    for diff in ("easy", "hard"):
        sub = [c for c in per_case if c["difficulty"] == diff]
        for tag in ("small", "large"):
            strategies.append(summarize([{**c[tag]} for c in sub], f"{tag}-only, {diff} cases only"))

    result = {
        "synthetic_data": True,
        "run_started": started.isoformat(timespec="seconds"),
        "timezone": str(started.tzinfo),
        "base_url": BASE_URL,
        "models": {"small": SMALL_MODEL, "large": LARGE_MODEL},
        "settings": {"temperature": 0, "max_tokens": MAX_TOKENS, "reasoning_effort": REASONING_EFFORT,
                     "runs_per_case": 1, "max_retries_on_429_or_5xx": MAX_RETRIES},
        "prices_usd_per_million_tokens": {
            "small": price["small"], "large": price["large"],
            "source": f"GET {BASE_URL}/models pricing field, read at run time; cross-check {PRICING_PAGE}"},
        "n_cases": len(per_case),
        "strategies": strategies,
        "cases": per_case,
    }
    (out / f"results{sfx}.json").write_text(json.dumps(result, indent=2))
    (out / f"results{sfx}.md").write_text(render_md(result))
    print(f"wrote results{sfx}.json and results{sfx}.md")
    return 0


def pct(x):
    return f"{x*100:.0f}%"


def render_md(r):
    p = r["prices_usd_per_million_tokens"]
    L = [f"# Model-routing benchmark: Crusoe Intelligence Foundry",
         "",
         f"Run: {r['run_started']} ({r['timezone']}). **All {r['n_cases']} tickets are synthetic**, modeled on public Crusoe support topics. One run per case at temperature 0, so this is a small-sample measurement, not a leaderboard.",
         "",
         f"- Small model: `{r['models']['small']}` at ${p['small']['input']:.2f} in / ${p['small']['output']:.2f} out per 1M tokens",
         f"- Large model: `{r['models']['large']}` at ${p['large']['input']:.2f} in / ${p['large']['output']:.2f} out per 1M tokens",
         f"- Price source: {p['source']}",
         f"- Settings: max_tokens={r['settings']['max_tokens']}, reasoning_effort={r['settings']['reasoning_effort']} for both; 429/5xx retried with exponential backoff",
         "",
         "| Strategy | Priority | Area | Team | All 3 correct | Priority within 1 | Failures | Avg latency (s) | Cost / ticket | Total cost | Large calls |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in r["strategies"]:
        L.append(f"| {s['strategy']} | {pct(s['acc_priority'])} | {pct(s['acc_area'])} | {pct(s['acc_team'])} | {pct(s['acc_all'])} | {pct(s['acc_priority_within1'])} | {s['failures']} | {s['avg_latency_s']:.2f} | ${s['cost_per_ticket_usd']:.6f} | ${s['total_cost_usd']:.5f} | {s['large_calls']} |")
    L += ["", "Routed rows: the oracle router uses the hand-assigned easy/hard label (an upper bound, not deployable). Heuristic rows decide from the small model's own output, so they pay for the small call plus the large call on escalated tickets; latency adds the same way.",
          "", "## Failures", ""]
    fails = [(c["id"], t, c[t]["failure"], c[t]["message"]) for c in r["cases"] for t in ("small", "large") if c[t]["failure"]]
    L += [f"- case {i} ({t}): {f}: {m}" for i, t, f, m in fails] or ["None."]
    L += ["", "## Per-case misses", "", "| Case | Difficulty | Expected | Small | Large |", "|---|---|---|---|---|"]
    def fmt(p):
        return "FAILED" if not p else f"{p['priority']}/{p['area']}/{p['team']}"
    for c in r["cases"]:
        e = c["expected"]
        exp = f"{e['priority']}/{e['area']}/{e['team']}"
        if c["small"]["score"]["all"] and c["large"]["score"]["all"]:
            continue
        L.append(f"| {c['id']} | {c['difficulty']} | {exp} | {fmt(c['small']['prediction'])} | {fmt(c['large']['prediction'])} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())
