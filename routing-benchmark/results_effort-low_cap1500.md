# Model-routing benchmark: Crusoe Intelligence Foundry

Run: 2026-11-28T07:29:25-08:00 (PST). **All 17 tickets are synthetic**, modeled on public Crusoe support topics. One run per case at temperature 0, so this is a small-sample measurement, not a leaderboard.

- Small model: `nvidia/Nemotron-3.5-Lightning-30B-A3B` at $0.05 in / $0.20 out per 1M tokens
- Large model: `zai-org/GLM-5.3` at $1.40 in / $4.40 out per 1M tokens
- Price source: GET https://api.inference.crusoecloud.com/v1/models pricing field, read at run time; cross-check https://www.crusoe.ai/cloud/pricing
- Settings: max_tokens=1500, reasoning_effort=low for both; 429/5xx retried with exponential backoff

| Strategy | Priority | Area | Team | All 3 correct | Priority within 1 | Failures | Avg latency (s) | Cost / ticket | Total cost | Large calls |
|---|---|---|---|---|---|---|---|---|---|---|
| small-only | 53% | 53% | 47% | 47% | 53% | 8 | 4.25 | $0.000284 | $0.00482 | 0 |
| large-only | 82% | 88% | 88% | 65% | 100% | 0 | 0.83 | $0.000781 | $0.01327 | 0 |
| routed: oracle (easy->small, hard->large) | 65% | 71% | 71% | 53% | 76% | 4 | 4.76 | $0.000741 | $0.01260 | 10 |
| routed: heuristic (small first; escalate on failure or confidence<=3) | 82% | 88% | 88% | 65% | 100% | 0 | 4.65 | $0.000662 | $0.01126 | 8 |
| routed: heuristic (small first; escalate if small says P1/P2 or fails) | 82% | 88% | 88% | 65% | 100% | 0 | 4.94 | $0.000937 | $0.01593 | 14 |
| small-only, easy cases only | 43% | 43% | 29% | 29% | 43% | 4 | 4.08 | $0.000275 | $0.00192 | 0 |
| large-only, easy cases only | 86% | 86% | 71% | 57% | 100% | 0 | 0.79 | $0.000785 | $0.00550 | 0 |
| small-only, hard cases only | 60% | 60% | 60% | 60% | 60% | 4 | 4.37 | $0.000290 | $0.00290 | 0 |
| large-only, hard cases only | 80% | 90% | 100% | 70% | 100% | 0 | 0.86 | $0.000778 | $0.00778 | 0 |

Routed rows: the oracle router uses the hand-assigned easy/hard label (an upper bound, not deployable). Heuristic rows decide from the small model's own output, so they pay for the small call plus the large call on escalated tickets; latency adds the same way.

## Failures

- case 2 (small): EmptyCompletion: [EmptyCompletion] HTTP 200 but the message content was empty (often reasoning consumed max_tokens).
- case 4 (small): EmptyCompletion: [EmptyCompletion] HTTP 200 but the message content was empty (often reasoning consumed max_tokens).
- case 5 (small): EmptyCompletion: [EmptyCompletion] HTTP 200 but the message content was empty (often reasoning consumed max_tokens).
- case 7 (small): EmptyCompletion: [EmptyCompletion] HTTP 200 but the message content was empty (often reasoning consumed max_tokens).
- case 8 (small): EmptyCompletion: [EmptyCompletion] HTTP 200 but the message content was empty (often reasoning consumed max_tokens).
- case 12 (small): EmptyCompletion: [EmptyCompletion] HTTP 200 but the message content was empty (often reasoning consumed max_tokens).
- case 14 (small): EmptyCompletion: [EmptyCompletion] HTTP 200 but the message content was empty (often reasoning consumed max_tokens).
- case 16 (small): EmptyCompletion: [EmptyCompletion] HTTP 200 but the message content was empty (often reasoning consumed max_tokens).

## Per-case misses

| Case | Difficulty | Expected | Small | Large |
|---|---|---|---|---|
| 2 | easy | P3/billing_quota/billing_quota_ops | FAILED | P3/billing_quota/billing_quota_ops |
| 3 | easy | P4/billing_quota/support_tier1 | P4/billing_quota/billing_quota_ops | P4/billing_quota/billing_quota_ops |
| 4 | easy | P3/inference/support_tier1 | FAILED | P3/billing_quota/billing_quota_ops |
| 5 | easy | P3/kubernetes/cmk_eng | FAILED | P3/kubernetes/cmk_eng |
| 7 | easy | P3/fine_tuning/support_tier1 | FAILED | P4/fine_tuning/support_tier1 |
| 8 | hard | P3/inference/support_tier1 | FAILED | P4/inference/support_tier1 |
| 12 | hard | P3/billing_quota/billing_quota_ops | FAILED | P2/billing_quota/billing_quota_ops |
| 14 | hard | P1/inference/security_oncall | FAILED | P1/billing_quota/security_oncall |
| 16 | hard | P2/billing_quota/billing_quota_ops | FAILED | P2/billing_quota/billing_quota_ops |
