# P1: Customer agents return blank answers after a model update

**This is a hypothetical practice postmortem.** It is not a real Crusoe incident, not a real customer case, and not a claim about a Crusoe outage. The customer, dollar impact, and ticket timeline below are invented for rehearsal. The technical reproduction is real: it uses the 21 November 2026 lab run on this account, recorded in `results.json`.

| Field | Value |
| --- | --- |
| Status | Resolved (practice) |
| Severity | P1 (hypothetical) |
| Product | Intelligence Foundry, Serverless Inference |
| Model used in the reproduction | `nvidia/Nemotron-3.5-Lightning-30B-A3B` |
| Cadence | Customer updates every 4 hours while P1 is open |
| Reproduction | Personal lab, 21 November 2026, 5:13 PM PT (America/Los_Angeles) |

## Summary

A hypothetical customer reported that their agents started returning blank answers after they moved to a newer reasoning model. HTTP checks stayed green. The lab reproduction showed HTTP 200 with `message.content` null, `finish_reason=length`, and the entire `max_tokens` budget spent on `reasoning_tokens`. Disabling reasoning returned a normal answer. Raising `max_tokens` from 64 to 512, while leaving `reasoning_effort=high`, did not.

## Impact

This impact figure is **hypothetical and illustrative only**. It is not a real customer loss and was not provided by Crusoe or by a real account.

Hypothetical customer impact: **$48,000** over a 6-hour window, described here as 12,000 failed agent turns at a fictional $4 fully loaded cost per failed turn, plus on-call overtime. In this story, a support and sales assistant stop completing replies, so users retry, abandon the session, or escalate to a human.

What was actually observed in the lab, and is not hypothetical:

- The API can return HTTP 200 with no customer-visible text.
- A monitor that only watches HTTP status would stay green.
- A tight token cap on a reasoning model is enough to create that shape.

## Detection

In this hypothetical, the customer opened a P1 after users reported blank agent replies. Their dashboards showed successful completions. Detection improved only after they started logging `message.content`, `finish_reason`, and `usage.completion_tokens_details.reasoning_tokens`.

The personal lab later added `healthcheck.py`, which fails on empty content, not just on HTTP errors. On the same day, a probe of `openai/gpt-oss-120b` with `max_tokens=32` and no `reasoning_effort` parameter reproduced the same empty-reply shape (see `healthcheck-output.txt`). That is additional real evidence, not part of the fictional customer timeline.

## Hypothetical timeline

All times are America/Los_Angeles, and the customer-facing times are invented. The 5:13 PM PT lab run is the real reproduction.

| Time | Event |
| --- | --- |
| 11:10 AM | Hypothetical: the customer switches a production agent from a non-reasoning default to a reasoning model, keeping `max_tokens=64`. |
| 11:40 AM | Hypothetical: users report blank answers. The customer's HTTP success rate remains ~100%. |
| 12:05 PM | Hypothetical: P1 opened with Crusoe support. Symptom: "API success, empty agent reply after a model update." |
| 12:15 PM | Hypothetical: first customer update. Investigating. Not declaring a regional outage. Next update in 4 hours or sooner. |
| 5:13:06–5:13:10 PM | **Real lab reproduction** on this account. `reasoning_effort=high`, `max_tokens=64` returned HTTP 200, `content` null, `finish_reason=length`, 64/64 completion tokens marked `reasoning_tokens`, 528 ms. |
| 5:13 PM | **Real workaround test.** `reasoning_effort=none`, `max_tokens=256` returned a full sentence (`finish_reason=stop`, 0 reasoning tokens) in 327 ms. `reasoning_effort=high`, `max_tokens=512` still returned empty content; all 512 tokens were reasoning. |
| 4:15 PM | Hypothetical: second customer update (T+4 hours from the 12:15 PM update) with the workaround and the evidence shape. |
| 6:00 PM | Hypothetical: customer applies `reasoning_effort=none` on paths that do not need a trace, and raises caps on paths that do. Blank replies stop in the story. |
| 8:15 PM | Hypothetical: third update, issue mitigated, P1 moved to monitoring, then closed. |

## Hypotheses and tests

| ID | Hypothesis | Test | Result |
| --- | --- | --- | --- |
| H1 | Platform outage or auth failure | Check HTTP status, try a known-good key, compare 401/404/429/503 shapes already reproduced in this lab | Hypothetical customer saw HTTP 200. Real lab: the empty reply itself is HTTP 200. Auth and model-name failures look different (401 and 404). |
| H2 | Request is being rate-limited or shed | Inspect `x-ratelimit-*` headers; look for 429 or 503 | A 25-request lab burst on this account was 26/26 HTTP 200. Documented meaning of 429 vs 503 is in https://docs.crusoe.ai/serverless-inference/rate-limits/. Not the shape of this incident. |
| H3 | Wrong or retired model ID after the update | Call `GET /v1/models` and compare IDs | A typo and a retired ID in this lab returned HTTP 404 `model_not_found`, not an empty 200. |
| H4 | Malformed client body after the update | Inspect `messages` and `max_tokens` types | Malformed bodies in this lab returned HTTP 400, not an empty 200. |
| H5 | Token budget is being spent on reasoning, so the visible answer never starts | Log `content`, `finish_reason`, and `reasoning_tokens`; compare `reasoning_effort=high` at 64 and 512 with `reasoning_effort=none` | **Confirmed in the lab.** 64-token high-reasoning call was empty. 512-token high-reasoning call was still empty. Disabling reasoning returned an answer. |

## Root cause

The user-visible failure was an empty assistant message on HTTP 200. In the lab, a reasoning model with a low `max_tokens` used the entire cap on a hidden trace and stopped with `finish_reason=length` before any visible text.

In the hypothetical story, a model update made this client setting unsafe: the app kept a cap that had been fine on a non-reasoning model, then moved to a reasoning default. This postmortem does not claim that Crusoe shipped a broken model or changed hidden defaults. It only claims what was measured: the empty-reply shape is real, and a modest increase in `max_tokens` is not always enough.

## Workaround

For paths that do not need a reasoning trace, set `reasoning_effort=none` (where the model accepts that parameter) and keep a modest cap. In the lab, that returned a complete answer in 327 ms.

For paths that need reasoning, raise `max_tokens` enough to cover the trace plus the answer. In the lab, 512 was still not enough on Nemotron 3.5 Lightning with `reasoning_effort=high`. Keep raising, or cap reasoning separately if the API supports it, and alert when `content` is empty and `finish_reason=length`.

Note from the healthcheck: `openai/gpt-oss-120b` rejected `reasoning_effort=none` with HTTP 400 (`Harmony does not support reasoning_effort='none'`). On that model, omitting the parameter and using `max_tokens=32` still produced an empty reply; raising the retry cap to 256 produced `ready`. Do not assume every catalog model accepts the same reasoning parameters.

## Long-term fix

Practice recommendations, not a claim about Crusoe's roadmap:

- Treat empty `content` on HTTP 200 as a first-class failure in client monitors. `healthcheck.py` in this repo does that.
- After any model ID or default-parameter change, re-run a short completion and assert that `content` is non-empty.
- Document that `max_tokens` counts reasoning tokens on reasoning models, and that `reasoning_effort` is model-dependent.
- Prefer listing `supported_parameters` from `GET /v1/models` before sending `reasoning_effort`. Crusoe's public support article on listing model features describes that field: https://support.crusoecloud.com/hc/en-us/articles/55002524169499-How-To-List-Model-Features-via-curl-and-the-Inference-API

## Customer communications

P1 updates every 4 hours, or sooner when there is a material change. The text below is a practice template, not a message that was sent to a real customer.

**T+0 (incident accepted):**

> We're investigating reports that agent completions return HTTP 200 with an empty assistant message after a model change. We have not identified a regional outage. We're checking response content, `finish_reason`, and token usage, not just HTTP status. Next update in 4 hours, or sooner if we have a fix.

**T+4 (workaround):**

> Early evidence shows the model can exhaust a low `max_tokens` budget on reasoning (`finish_reason=length`, `content` null), which still looks like success on HTTP 200. Workaround: set `reasoning_effort` to `none` or `low` if you do not need a reasoning trace, or raise `max_tokens` enough to cover reasoning plus the answer. In our reproduction, raising the cap to 512 with high reasoning was not enough; disabling reasoning was. Next update in 4 hours, or sooner if the workaround is confirmed on your traffic.

**T+8 (mitigated):**

> The blank replies are consistent with a reasoning token budget issue rather than an authentication, catalog, or rate-limit failure. Please keep the workaround in place, and monitor for empty `content` even when HTTP status is 200. We are closing this P1 and will follow up on documentation and monitor coverage. If blank replies continue after a generous cap and lower reasoning effort, we will reopen and escalate to engineering.

## Prevention and action items

| Item | Owner in this practice kit | Due |
| --- | --- | --- |
| Keep `healthcheck.py` asserting non-empty `content` on cheap models | This repo | Done, with a live capture in `healthcheck-output.txt` |
| Write the empty-reply case into the 5-minute walkthrough | `DEMO.md` | Done |
| File the docs and API-shape findings as feedback tickets | `VOICE_OF_CUSTOMER.md` | Done |
| After any model change in a real environment, rerun a short "reply with ready" probe and fail on empty `content` | Customer or operator | Recurring |

Again: the incident story and the $48,000 figure are hypothetical. The HTTP 200 / null content / `finish_reason=length` evidence is from the real lab run on this account.
