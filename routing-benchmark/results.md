# Model-routing benchmark: Crusoe Intelligence Foundry

Run: 2026-11-28T07:32:29-08:00 (PST). **All 17 tickets are synthetic**, modeled on public Crusoe support topics. One run per case at temperature 0, so this is a small-sample measurement, not a leaderboard.

- Small model: `nvidia/Nemotron-3.5-Lightning-30B-A3B` at $0.05 in / $0.20 out per 1M tokens
- Large model: `zai-org/GLM-5.3` at $1.40 in / $4.40 out per 1M tokens
- Price source: GET https://api.inference.crusoecloud.com/v1/models pricing field, read at run time; cross-check https://www.crusoe.ai/cloud/pricing
- Settings: max_tokens=4000, reasoning_effort=low for both; 429/5xx retried with exponential backoff

| Strategy | Priority | Area | Team | All 3 correct | Priority within 1 | Failures | Avg latency (s) | Cost / ticket | Total cost | Large calls |
|---|---|---|---|---|---|---|---|---|---|---|
| small-only | 88% | 88% | 71% | 65% | 100% | 0 | 5.31 | $0.000354 | $0.00602 | 0 |
| large-only | 82% | 88% | 88% | 65% | 100% | 0 | 0.77 | $0.000762 | $0.01295 | 0 |
| routed: oracle (easy->small, hard->large) | 82% | 88% | 82% | 65% | 100% | 0 | 5.77 | $0.000806 | $0.01371 | 10 |
| routed: heuristic (small first; escalate on failure or confidence<=3) | 88% | 88% | 71% | 65% | 100% | 0 | 5.41 | $0.000451 | $0.00766 | 2 |
| routed: heuristic (small first; escalate if small says P1/P2 or fails) | 88% | 88% | 76% | 65% | 100% | 0 | 5.71 | $0.000752 | $0.01278 | 9 |
| small-only, easy cases only | 86% | 86% | 57% | 57% | 100% | 0 | 5.33 | $0.000353 | $0.00247 | 0 |
| large-only, easy cases only | 86% | 86% | 71% | 57% | 100% | 0 | 0.75 | $0.000751 | $0.00526 | 0 |
| small-only, hard cases only | 90% | 90% | 80% | 70% | 100% | 0 | 5.29 | $0.000355 | $0.00355 | 0 |
| large-only, hard cases only | 80% | 90% | 100% | 70% | 100% | 0 | 0.78 | $0.000769 | $0.00769 | 0 |

Routed rows: the oracle router uses the hand-assigned easy/hard label (an upper bound, not deployable). Heuristic rows decide from the small model's own output, so they pay for the small call plus the large call on escalated tickets; latency adds the same way.

## Failures

None.

## Per-case misses

| Case | Difficulty | Expected | Small | Large |
|---|---|---|---|---|
| 3 | easy | P4/billing_quota/support_tier1 | P4/billing_quota/billing_quota_ops | P4/billing_quota/billing_quota_ops |
| 4 | easy | P3/inference/support_tier1 | P3/billing_quota/billing_quota_ops | P3/billing_quota/billing_quota_ops |
| 7 | easy | P3/fine_tuning/support_tier1 | P4/fine_tuning/ml_platform_eng | P4/fine_tuning/support_tier1 |
| 8 | hard | P3/inference/support_tier1 | P3/inference/inference_eng | P4/inference/support_tier1 |
| 12 | hard | P3/billing_quota/billing_quota_ops | P2/billing_quota/billing_quota_ops | P2/billing_quota/billing_quota_ops |
| 14 | hard | P1/inference/security_oncall | P1/inference/security_oncall | P1/billing_quota/security_oncall |
| 16 | hard | P2/billing_quota/billing_quota_ops | P2/gpu_vm/compute_oncall | P2/billing_quota/billing_quota_ops |
