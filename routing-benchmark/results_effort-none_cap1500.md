# Model-routing benchmark: Crusoe Intelligence Foundry

Run: 2026-11-28T07:31:18-08:00 (PST). **All 17 tickets are synthetic**, modeled on public Crusoe support topics. One run per case at temperature 0, so this is a small-sample measurement, not a leaderboard.

- Small model: `nvidia/Nemotron-3.5-Lightning-30B-A3B` at $0.05 in / $0.20 out per 1M tokens
- Large model: `zai-org/GLM-5.3` at $1.40 in / $4.40 out per 1M tokens
- Price source: GET https://api.inference.crusoecloud.com/v1/models pricing field, read at run time; cross-check https://www.crusoe.ai/cloud/pricing
- Settings: max_tokens=1500, reasoning_effort=none for both; 429/5xx retried with exponential backoff

| Strategy | Priority | Area | Team | All 3 correct | Priority within 1 | Failures | Avg latency (s) | Cost / ticket | Total cost | Large calls |
|---|---|---|---|---|---|---|---|---|---|---|
| small-only | 59% | 94% | 76% | 47% | 94% | 1 | 0.26 | $0.000030 | $0.00050 | 0 |
| large-only | 82% | 94% | 88% | 71% | 100% | 0 | 3.92 | $0.002805 | $0.04768 | 0 |
| routed: oracle (easy->small, hard->large) | 65% | 100% | 88% | 59% | 100% | 0 | 2.57 | $0.001692 | $0.02877 | 10 |
| routed: heuristic (small first; escalate on failure or confidence<=3) | 71% | 94% | 82% | 53% | 100% | 0 | 1.21 | $0.000694 | $0.01180 | 3 |
| routed: heuristic (small first; escalate if small says P1/P2 or fails) | 71% | 100% | 82% | 59% | 100% | 0 | 2.20 | $0.001408 | $0.02394 | 8 |
| small-only, easy cases only | 43% | 100% | 71% | 29% | 100% | 0 | 0.27 | $0.000029 | $0.00020 | 0 |
| large-only, easy cases only | 86% | 86% | 71% | 57% | 100% | 0 | 3.92 | $0.002773 | $0.01941 | 0 |
| small-only, hard cases only | 70% | 90% | 80% | 60% | 90% | 1 | 0.26 | $0.000030 | $0.00030 | 0 |
| large-only, hard cases only | 80% | 100% | 100% | 80% | 100% | 0 | 3.92 | $0.002827 | $0.02827 | 0 |

Routed rows: the oracle router uses the hand-assigned easy/hard label (an upper bound, not deployable). Heuristic rows decide from the small model's own output, so they pay for the small call plus the large call on escalated tickets; latency adds the same way.

## Failures

- case 14 (small): UnparseableTriage: [UnparseableTriage] The reply was not a JSON object with valid priority/area/team values. (value outside the allowed labels)

## Per-case misses

| Case | Difficulty | Expected | Small | Large |
|---|---|---|---|---|
| 2 | easy | P3/billing_quota/billing_quota_ops | P4/billing_quota/billing_quota_ops | P3/billing_quota/billing_quota_ops |
| 3 | easy | P4/billing_quota/support_tier1 | P4/billing_quota/billing_quota_ops | P4/billing_quota/billing_quota_ops |
| 4 | easy | P3/inference/support_tier1 | P4/inference/inference_eng | P3/billing_quota/billing_quota_ops |
| 6 | easy | P1/networking/network_eng | P2/networking/network_eng | P1/networking/network_eng |
| 7 | easy | P3/fine_tuning/support_tier1 | P4/fine_tuning/support_tier1 | P4/fine_tuning/support_tier1 |
| 8 | hard | P3/inference/support_tier1 | P3/inference/inference_eng | P4/inference/support_tier1 |
| 11 | hard | P2/inference/inference_eng | P3/inference/inference_eng | P2/inference/inference_eng |
| 12 | hard | P3/billing_quota/billing_quota_ops | P2/billing_quota/billing_quota_ops | P2/billing_quota/billing_quota_ops |
| 14 | hard | P1/inference/security_oncall | FAILED | P1/inference/security_oncall |
