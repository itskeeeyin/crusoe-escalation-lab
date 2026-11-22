# Example escalation: HTTP 200 with a blank assistant message

This is an example customer escalation built from a **public Crusoe known-issue write-up** and a **real reproduction** on this account on 21 November 2026 at 6:36 PM PT (America/Los_Angeles). The customer name and any dollar impact below are **hypothetical**. The API evidence is not.

Suggested severity: **P1**. The inference API stays up and returns HTTP 200, so error-rate dashboards stay green, while users get a blank answer. That is a production workflow break with a silent failure mode. It is not a P0: the endpoint is reachable, and a workaround exists. P1 customer updates every 4 hours.

## Source (real public report)

Crusoe Support, "LLM Capabilities - Image / Text / Browser Control in MI," updated 30 September 2026:

https://support.crusoecloud.com/hc/en-us/articles/56524456657947-LLM-Capabilities-Image-Text-Browser-Control-in-MI

The article documents reasoning models that "spend output tokens thinking before they answer, and with a small `max_tokens` (under a few hundred) the budget runs out mid-thought and `message.content` comes back `None` — which is easy to mistake for 'the model ignored my image.'"

Under Common Issues it says: "`message.content` is `None` or empty after an image question — a reasoning model ran out of `max_tokens` while thinking. Check `finish_reason == 'length'` and raise `max_tokens` to 1024 or more."

The article names Nemotron 3 Nano Omni, Kimi K2.6, Qwen3.8 27B, and GLM-5.3 Flash in that note. This lab reproduced the same mechanism on `nvidia/Nemotron-3.5-Lightning-30B-A3B` with a **text** prompt, to keep spend tiny and avoid image tokens. It does not claim an image was sent in this run.

## Customer symptom

Hypothetical customer: a team ships an agent that calls Serverless Inference. After they move to a reasoning model, or after they start sending image questions, users report blank answers. Their monitors show HTTP 200. They open a P1: "the model is ignoring our question" or "the model ignored my image."

## Reproduction evidence

Personal lab, this account, 6:36:16–6:36:21 PM PT, model `nvidia/Nemotron-3.5-Lightning-30B-A3B`, base URL `https://api.inference.crusoecloud.com/v1`. Raw redacted calls are in `escalations/repro-results.json`.

| Attempt | Settings | HTTP | Content | Finish | Usage | Latency |
| --- | --- | --- | --- | --- | --- | --- |
| Break | `reasoning_effort=high`, `max_tokens=64` | 200 | `null` | `length` | 49 prompt, 64 completion, all 64 `reasoning_tokens` | 671 ms |
| Official recommended fix | `reasoning_effort=high`, `max_tokens=1024` | 200 | Partial text (930 characters), cut off mid-sentence | `length` | 49 prompt, 1024 completion, 830 `reasoning_tokens` | 3.68 s |

On the 64-token call, a `reasoning` field was present and had been cut off mid-thought. That matches the article: the budget ran out during thinking, and `message.content` was `None`.

On the 1024-token call, the official advice was enough to get *some* visible text, but not a complete answer. `finish_reason` was still `length`. The model spent 830 tokens on reasoning, then started a step-by-step write-up in `content` and was cut off at "and steers." The user had asked for a one-sentence answer.

An earlier lab run the same day (5:13 PM PT, in `results.json`) already showed the same empty 64-token case, and showed that `reasoning_effort=none` with `max_tokens=256` returned a complete sentence (`finish_reason=stop`, 0 reasoning tokens) in 327 ms. Raising the cap to 512 with high reasoning had also failed (all 512 tokens were still reasoning).

## Hypotheses and tests

| ID | Hypothesis | Test | Result |
| --- | --- | --- | --- |
| H1 | The API is down or the key is bad | Check HTTP status and a known-good short call | HTTP 200 on the failing call. A later benign "Say hi in three words" call on the same host returned HTTP 200 with visible text in 182 ms. |
| H2 | The model ID is wrong or retired | Compare to `GET /v1/models` | The ID `nvidia/Nemotron-3.5-Lightning-30B-A3B` is in the current catalog. Wrong IDs in the earlier lab returned HTTP 404 `model_not_found`, not an empty 200. |
| H3 | The request is rate-limited or shed | Inspect status and `x-ratelimit-*` headers | No 429 or 503. Remaining request capacity stayed high (599 of 600). |
| H4 | A small `max_tokens` is consumed by reasoning, so `content` is empty and `finish_reason` is `length` | Send the same prompt at 64 and at the article's 1024 cap; inspect `reasoning_tokens` | **Confirmed.** 64 tokens: `content` null, 64/64 reasoning. 1024 tokens: content present but still `finish_reason=length`, 830 reasoning tokens. |
| H5 | Disabling reasoning is a more reliable workaround when a trace is not required | Earlier lab: `reasoning_effort=none`, `max_tokens=256` | **Confirmed** in the 5:13 PM PT run: complete answer, `finish_reason=stop`. |

## Workaround

- If the product does not need a hidden reasoning trace, set `reasoning_effort=none` or `low` on models that accept that parameter. In the earlier lab, that returned a complete answer at `max_tokens=256`.
- If the product needs reasoning, do not stop at 1024 without checking `finish_reason`. In this run, 1024 still truncated the answer. Raise the cap further, or cap reasoning separately if the API allows it, and retry when `finish_reason` is `length`.
- Treat empty or clearly truncated `content` on HTTP 200 as a client-side failure. `healthcheck.py` in this repo does that.

Note: `openai/gpt-oss-120b` rejected `reasoning_effort=none` with HTTP 400 in the healthcheck the same day. Confirm `supported_parameters` before sending that field.

## Long-term fix and engineering ask

Practice recommendations, not a claim about Crusoe's roadmap:

- Keep the Common Issues note, and extend it so it is not only framed as an image problem. The same empty-content shape happens on a text-only prompt.
- Soften "raise `max_tokens` to 1024 or more" to "start at 1024, then check `finish_reason` and `reasoning_tokens`. 1024 may still truncate the visible answer." This lab is a worked example.
- Recommend the second lever, `reasoning_effort`, for callers who do not need a trace, and say that the parameter is model-dependent.
- Consider a warning when `finish_reason=length` and `content` is null or clearly incomplete, so HTTP-only monitors can see it.

## Customer updates (P1, every 4 hours)

Hypothetical comms. No real customer received these.

**T+0:**

> We're investigating reports of blank assistant messages on Serverless Inference. HTTP status on the samples we have is 200, so this does not look like a regional outage or an authentication failure. We're checking `message.content`, `finish_reason`, and reasoning token usage. Next update in 4 hours, or sooner if we have a workaround.

**T+4:**

> This matches a documented reasoning-budget issue: with a small `max_tokens`, the model can spend the whole cap on thinking and return `content` null with `finish_reason=length`. Crusoe's public Common Issues note describes that shape and suggests raising `max_tokens` to 1024 or more. In our reproduction, 64 tokens returned a blank message; 1024 returned partial text that was still cut off (`finish_reason` was still `length`). Workaround: if you do not need a reasoning trace, set `reasoning_effort` to `none` or `low` where the model allows it; if you do, raise the cap past 1024 and retry whenever `finish_reason` is `length`. Next update in 4 hours, or sooner if you confirm the workaround.

**T+8 (mitigated):**

> The blank replies are consistent with a reasoning token budget issue, not with an outage, a bad key, or a missing model ID. Please keep the workaround in place and alert on empty or truncated `content` even when HTTP status is 200. We're closing this P1 and asking docs/engineering to clarify that 1024 is a starting point, not always a complete fix. If blank replies continue after a generous cap and lower reasoning effort, we will reopen and escalate.

## Lessons

- HTTP 200 is not the same as "the user got an answer." Collect `content`, `finish_reason`, and `reasoning_tokens` on day one.
- A vendor-recommended cap can still be too small. Test it, and say so if it only partly works.
- The public article is easy to file under "vision," but the failure is about reasoning budgets. A text-only reproduction is enough to confirm it, and cheaper.

Spend for this reproduction, including the endpoint checks in the companion write-up: about **$0.000237** (168 prompt / 1,143 completion tokens) on Nemotron 3.5 Lightning at $0.05 / $0.20 per million tokens.
