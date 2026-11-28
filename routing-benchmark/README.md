# Model-routing benchmark: Crusoe Intelligence Foundry

A small, measured benchmark for `crusoe-escalation-lab`: does routing support-triage tickets between a small and a large Foundry model save money without losing accuracy?

**All 17 tickets in `cases.py` are synthetic.** They are modeled on public Crusoe support topics (GPU VM won't boot, quota exceeded, stopped instance still billing, CMK autoscaler, load balancer health checks, fine-tune validation, Serverless Inference 429 and empty completions). One run per case at temperature 0, so treat results as a measurement of this set, not a leaderboard.

## Run it

```bash
export CRUSOE_API_KEY=...   # Intelligence API key; never printed or written by the script
python bench.py --reasoning-effort low --max-tokens 4000 --tag effort-low_cap4000
python bench.py --dry-run   # plan only, no calls
```

Stdlib only. Endpoint: `https://api.inference.crusoecloud.com/v1` (OpenAI-compatible). Prices are read at run time from `GET /v1/models` (`pricing`, USD per 1M tokens) and match the Serverless Inference table on https://www.crusoe.ai/cloud/pricing (checked 28 Nov 2026).

## Setup

- Small: `nvidia/Nemotron-3.5-Lightning-30B-A3B`, $0.05 in / $0.20 out per 1M tokens
- Large: `zai-org/GLM-5.3`, $1.40 in / $4.40 out per 1M tokens
- Task: JSON triage with priority (P1-P4 by impact x urgency), product area, escalate-to team, and a 1-5 confidence.
- Failure classes: `FoundryKeyMissing`, `FoundryAuthFailed`, `FoundryRateLimited` (429 retried with exponential backoff, honoring `Retry-After`), `FoundryServerBusy`, `FoundryRequestRejected`, `FoundryNetworkError`, `EmptyCompletion`, `UnparseableTriage`. A failed call scores 0 on all fields.
- Routers: *oracle* sends hand-labeled hard cases to large (an upper bound, not deployable). *Heuristic* rows run small first and escalate to large on a failure, on low confidence (<=3), or when small says P1/P2; they pay for both calls.

## Results (three runs, same 17 cases)

Headline run, `reasoning_effort=low`, `max_tokens=4000` (`results_effort-low_cap4000.md/json`):

| Strategy | All 3 correct | Priority | Area | Team | Failures | Avg latency | Cost/ticket | Total |
|---|---|---|---|---|---|---|---|---|
| small-only | 65% | 88% | 88% | 71% | 0 | 5.31 s | $0.000354 | $0.00602 |
| large-only | 65% | 82% | 88% | 88% | 0 | 0.77 s | $0.000762 | $0.01295 |
| routed, oracle | 65% | 82% | 88% | 82% | 0 | 5.77 s | $0.000806 | $0.01371 |
| routed, confidence heuristic | 65% | 88% | 88% | 71% | 0 | 5.41 s | $0.000451 | $0.00766 |
| routed, P1/P2 heuristic | 65% | 88% | 88% | 76% | 0 | 5.71 s | $0.000752 | $0.01278 |

Other runs (full tables in the `results_*.md` files):

- `effort-low, cap 1500`: the small model spends 800-1,500 tokens on hidden reasoning even at `low`, hit the cap on 8 of 17 tickets and returned `EmptyCompletion`. Small-only: 47% all-correct with 8 failures; large-only 65%.
- `effort-none, cap 1500`: the small model answers in ~0.26 s for $0.00003 per ticket (all-correct 47%, one `UnparseableTriage`), while the large model took 3.9 s and $0.0028 per ticket, so `none` did not make GLM-5.3 cheaper or faster in this test. Large-only 71% all-correct.

Total spend across the three runs: about $0.085.

## Caveats

- Labels are hand-assigned. Cases 3, 4, 7, 8 and 12 were missed by both models in the headline run, which points to ambiguous labels (e.g. a documented rate limit could reasonably go to billing or tier-1) rather than only model error.
- n=17, one run each. Differences of one or two tickets are noise.
- Latency was measured sequentially from one machine and mixes model speed with reasoning length.
- The "easy" and "hard" labels did not separate the models well here, so the oracle router saved nothing.

## Takeaway

Accuracy on this set was a tie (65% all-fields-correct); the cheapest option that matched it was small-first with confidence-based escalation (about 41% cheaper than large-only), but the small model's hidden reasoning makes `max_tokens` and `reasoning_effort` the real operating risks.
