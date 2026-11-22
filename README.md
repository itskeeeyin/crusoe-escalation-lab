# Crusoe escalation practice lab

Personal lab for reproducing common Crusoe Serverless Inference issues against your own Intelligence API account. It records live, redacted evidence and names each finding with a human-readable failure class such as `[empty_reply]` or `[auth_failure]`.

This is not a Crusoe-internal document, and it does not claim platform behavior beyond what the API returned in this lab plus [public Serverless rate-limit docs](https://docs.crusoe.ai/serverless-inference/rate-limits/). The included `results.json` is a scrubbed snapshot from a run on 21 November 2026 at 5:13 PM PT (America/Los_Angeles) on the operator's own account.

## Contents

- [`practice_lab.py`](practice_lab.py) — live reproductions of common Serverless Inference failures, with named issue classes and redacted `results.json`
- [`DEMO.md`](DEMO.md) — a 5-minute walkthrough of the empty-reply case: triage, root cause, customer update
- [`postmortems/P1-blank-agent-responses.md`](postmortems/P1-blank-agent-responses.md) — a **hypothetical** P1 postmortem that uses the real lab evidence as its reproduction
- [`VOICE_OF_CUSTOMER.md`](VOICE_OF_CUSTOMER.md) — new-user friction, written as docs and engineering feedback tickets
- [`healthcheck.py`](healthcheck.py) — synthetic monitor for latency, HTTP errors, and empty content; live output is in [`healthcheck-output.txt`](healthcheck-output.txt)
- [`PLAN_30_60_90.md`](PLAN_30_60_90.md) — a personal 30/60/90-day plan for a Senior Escalation Manager role
- [`INTERVIEW_QUESTIONS.md`](INTERVIEW_QUESTIONS.md) — questions by public product area
- [`escalations/`](escalations/) — example customer escalations built from public Crusoe reports plus a real lab reproduction
- [`tests/`](tests/) — offline unit tests, no API key required

## How to run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export CRUSOE_API_KEY=...    # Intelligence API key; never commit or paste this
python practice_lab.py
```

The script reads the key only from the environment, writes redacted evidence to `results.json`, and refuses to write the file if the key appears in the payload. Offline tests need no key:

```bash
python -m unittest discover -s tests -v
```

A GitHub Actions workflow that runs the same command, with no API key, is in [`ci/github-actions.yml`](ci/github-actions.yml). Copy it to `.github/workflows/ci.yml` to enable Actions on the repo.

Optional flags: `--burst 25` (capped at 30), `--skip-burst`, `--model nvidia/Nemotron-3.5-Lightning-30B-A3B`.

Default base URL: `https://api.inference.crusoecloud.com/v1` (OpenAI-compatible). The lab sticks to cheap models. The snapshot below used `nvidia/Nemotron-3.5-Lightning-30B-A3B` ($0.05 input / $0.20 output per million tokens) and cost about **$0.000177** (638 prompt tokens, 725 completion tokens).

## Lab snapshot, 21 November 2026

| Scenario | Reproduced | What we saw |
| --- | --- | --- |
| Empty reply | Yes | HTTP 200, `content` null, `finish_reason=length` |
| Wrong or deprecated model | Yes | HTTP 404, `model_not_found` |
| Bad or missing API key | Yes | HTTP 401, `Authentication failed` |
| Rate limits | 429 not observed | 25-request burst, all HTTP 200; headers showed 600 RPM / 2,000,000 TPM |
| Latency and streaming | Yes | Stream TTFT 42 ms; non-stream 154 ms |
| Malformed request | Yes | HTTP 400, `invalid_request_error` |

### Empty reply

- **Symptom.** The API returns success, but the customer gets no assistant text.
- **Evidence.** `reasoning_effort=high` and `max_tokens=64` returned HTTP 200 in 528 ms. `message.content` was null, `finish_reason` was `length`, and all 64 completion tokens were `reasoning_tokens`. A reasoning trace was present; it had been cut off mid-thought.
- **Root cause.** The token budget was spent on reasoning, so the visible answer never started. This still looks like success because the HTTP status is 200.
- **Workaround.** Setting `reasoning_effort=none` with `max_tokens=256` returned a full one-sentence answer (`finish_reason=stop`, 0 reasoning tokens) in 327 ms. Raising the cap to `max_tokens=512` while leaving `reasoning_effort=high` was **not** enough: the model used all 512 tokens on reasoning and returned an empty `content` string with `finish_reason=length`. If the product needs reasoning, the cap has to cover the trace plus the answer, not just a slightly larger number.
- **Customer update.** "We're investigating chat completions that return HTTP 200 with an empty assistant message. Early evidence shows the model exhausting a low `max_tokens` budget on reasoning (`finish_reason=length`, `content` null) rather than a platform outage. Workaround: raise `max_tokens` enough to cover reasoning plus the answer, or set `reasoning_effort` to `none` or `low` if you do not need a reasoning trace. Next update in 4 hours, or sooner if we have a fix."

### Wrong or deprecated model name

- **Symptom.** Completions fail as soon as the app starts, or after a model retirement.
- **Evidence.** `nvidia/Nemotron-3.5-Lightning-30B` (missing the `-A3B` suffix) and `nvidia/Nemotron-3-Nano` (a retired name) both returned HTTP 404 with `code: model_not_found` and a message of the form `Model not found: <id>`.
- **Root cause.** The model ID is not in the current Serverless catalog. In this lab the typo and the retired name used the same error shape, so the status code alone does not tell you which it is.
- **Workaround.** Call `GET /v1/models` and use an ID from that list. Confirm the string character-for-character, including org prefix and suffix.
- **Customer update.** "We're investigating inference calls that return HTTP 404 with `model_not_found`. That matches a model ID that is not in the current Serverless catalog, including typos and retired names. Please list models from `GET /v1/models` and switch to a currently listed ID. Next update in 4 hours, or sooner if we confirm a catalog issue."

### Bad or missing API key

- **Symptom.** Every call fails with an auth error, often right after a key rotation or a missing header.
- **Evidence.** An obviously fake key (`sk-crusoe-practice-fake-key-not-real`, not a real credential) returned HTTP 401 with `{"errors": ["Authentication failed"], "id": "..."}` in 84 ms. Omitting the `Authorization` header also returned HTTP 401 with `{"errors": ["Authentication failed"]}`.
- **Root cause.** The request is not authenticated. This is a credential or header problem, not a model outage.
- **Workaround.** Create a key in Intelligence Foundry → Inference, send it as `Authorization: Bearer <key>` to `https://api.inference.crusoecloud.com/v1`, and keep it out of source control. After a rotation, update the environment and restart the process.
- **Customer update.** "We're investigating HTTP 401 `Authentication failed` responses. That is consistent with a missing or invalid Intelligence API key, not with a model outage. Please confirm the key was created in Intelligence Foundry, is still active, and is sent as `Authorization: Bearer <key>` to `https://api.inference.crusoecloud.com/v1`. Next update in 4 hours, or sooner if valid keys are failing."

### Rate limits

- **Symptom.** Intermittent failures under load, often HTTP 429, sometimes HTTP 503.
- **Evidence.** A burst of 25 tiny requests, plus the probe, returned HTTP 200 on all 26 calls. No 429 or 503 was observed, and this lab did not send more than 30 burst requests. Observed headers on this account: `x-ratelimit-limit-requests=600`, `x-ratelimit-limit-tokens=2000000`, plus `x-ratelimit-limit-output-tokens=200000`. Remaining requests went from 599 to 580 during the run.
- **Root cause.** Those header limits match Crusoe's documented defaults when a payment method is on file (600 RPM and 2,000,000 TPM per project per model). The no-payment-method defaults are 30 RPM and 500,000 TPM. A 25-request burst is well under a 600 RPM cap, so a 429 was not expected. Documented meaning of the status codes: 429 means the project exceeded TPM or RPM; 503 means the request is within limits but the shared endpoint is under high load.
- **Workaround.** Read the rate-limit headers and throttle client-side. Retry 429 and 503 with exponential backoff and jitter. Limits reset each minute. If launch traffic will exceed the defaults, request a limit increase or use reserved capacity, as described in the public docs.
- **Customer update.** "We're watching Serverless Inference rate limiting. A short lab burst did not return HTTP 429; response headers showed a 600 request-per-minute and 2,000,000 token-per-minute cap, which matches Crusoe's documented defaults when a payment method is on file. If you are seeing 429s, check `x-ratelimit-remaining-requests` and retry with exponential backoff. HTTP 503 is different: you are within quota, but the shared endpoint is busy. Next update in 4 hours, or sooner if we see errors under those limits."

### Latency and streaming

- **Symptom.** The app feels slow, or streaming appears to hang before the first token.
- **Evidence.** Same short prompt, `reasoning_effort=none`. Non-streaming: HTTP 200 in 154 ms, content `ready`. Streaming: time to first SSE line 42 ms, full response 121 ms, 4 events, first content on event 2, content `ready`.
- **Root cause.** End-to-end time is not the same as time to first token. Reasoning models can also spend a long time on a hidden trace before any visible text, which looks like slowness even when the call succeeds.
- **Workaround.** Measure TTFT on the stream, not just total latency. Compare streaming and non-streaming. If reasoning is enabled, watch for the empty-reply pattern above.
- **Customer update.** "We're reviewing reports of slow or stalled completions. In this lab a short non-streaming call finished in 154 ms, and the streaming call's first token arrived in 42 ms. If your time-to-first-token is much higher, we'll compare stream versus non-stream, check reasoning spend, and look for 429 or 503. Next update in 4 hours, or sooner with findings."

### Malformed request

- **Symptom.** A client change starts returning HTTP 400, often on every call.
- **Evidence.** Sending `messages` as a string returned HTTP 400 `invalid_request_error`: `Missing or invalid 'messages' array (fail_to_proxy)` in 17 ms. Sending `max_tokens: -1` returned HTTP 400 `json_parse_error`: `max_tokens: invalid value: integer -1, expected u32` in 62 ms.
- **Root cause.** The JSON body does not match the OpenAI-compatible schema. This is a client payload issue, not an outage.
- **Workaround.** Validate the request body. `messages` must be an array of role/content objects, and `max_tokens` must be a positive integer.
- **Customer update.** "We're investigating HTTP 400 `invalid_request_error` responses. Lab tests show a malformed body is rejected immediately (`messages` not an array, or `max_tokens=-1`). This is a client payload issue, not an outage. We'll help validate the request against the OpenAI-compatible schema. Next update in 4 hours, or once the payload is corrected."

## When to escalate to Crusoe engineering

Stay with the customer or your own client fix when the evidence matches a typo'd model ID, a bad key, a malformed body, a low `max_tokens` on a reasoning model, or a 429 that lines up with the remaining quota in the headers.

Escalate when a currently listed model ID returns 404, a known-good key returns 401, a documented-valid payload returns 400, HTTP 200 empty replies continue after a generous token cap and lower reasoning effort, 429s appear well under the limits in the headers, or 503s persist after backoff.

## Credits and redaction

Cost in the snapshot was estimated from the `usage` fields and the per-model prices returned by `GET /v1/models` ($0.05 / $0.20 per million tokens for Nemotron 3.5 Lightning). `results.json` has the API key, `Authorization` headers, and account or org IDs stripped. Do not commit a live key. If you rerun the lab, keep the new `results.json` out of git until you have confirmed it is scrubbed.

## 5-minute walkthrough

[`DEMO.md`](DEMO.md) is a timed script for walking through the empty-reply case live: triage on HTTP 200 with null `content`, root cause (reasoning consumed the token budget; raising `max_tokens` to 512 was not enough), then a P1 customer update on a 4-hour cadence.

## Hypothetical P1 postmortem

[`postmortems/P1-blank-agent-responses.md`](postmortems/P1-blank-agent-responses.md) is labelled hypothetical. The customer, the dollar figure, and the ticket timeline are invented for practice. The reproduction inside it is the real 21 November 2026 lab run.

## Voice of the customer

[`VOICE_OF_CUSTOMER.md`](VOICE_OF_CUSTOMER.md) turns friction from this signup and lab into feedback tickets, including:

- The [create-an-account](https://docs.crusoe.ai/create-an-account.md) page says you must add a payment method to use managed inference; the [19 August 2026 updates entry](https://docs.crusoe.ai/updates/2026/august/) says introductory credits work without a payment method.
- HTTP 200 with null `content` when reasoning exhausts `max_tokens`.
- Raising `max_tokens` to 512 did not fix it; `reasoning_effort=none` did.
- `openai/gpt-oss-120b` rejected `reasoning_effort=none` with HTTP 400, then returned the same empty-reply shape at `max_tokens=32`.

## Healthcheck

`healthcheck.py` probes cheap models for HTTP errors, empty assistant content, and high latency. It prints a status table and exits non-zero with named issue classes such as `[empty_reply]`, `[http_error]`, or `[high_latency]`. Default is a single run; `--interval 60` loops.

```bash
export CRUSOE_API_KEY=...    # never commit or paste this
python healthcheck.py
python healthcheck.py --interval 60 --max-runs 3
```

A live capture from 21 November 2026 is in [`healthcheck-output.txt`](healthcheck-output.txt). Combined usage for those healthcheck runs was under $0.00004. Nemotron 3.5 Lightning was healthy on a short `reasoning_effort=none` probe. `openai/gpt-oss-120b` first returned HTTP 400 on `reasoning_effort=none`, then an empty HTTP 200 at `max_tokens=32`, and then a normal `ready` once the retry cap was raised to 256.

## 30 / 60 / 90-day plan

[`PLAN_30_60_90.md`](PLAN_30_60_90.md) is a personal plan for a Senior Escalation Manager role, covering a practice severity matrix, an escalation playbook, an engineering feedback loop, comms templates, and metrics. It is grounded in public Crusoe products (Intelligence Foundry, CMK, GPU VMs, Managed Slurm, storage) and does not quote confidential material from prior roles.

## Interview questions

[`INTERVIEW_QUESTIONS.md`](INTERVIEW_QUESTIONS.md) lists questions by product area: Serverless Inference, CMK, GPU VMs, Managed Slurm, storage, and cross-product docs and cadence.

## Example customer escalations

Two practice escalations in [`escalations/`](escalations/) start from public Crusoe support or community reports, then use a real reproduction on this account. Customer names and dollar figures in those write-ups are hypothetical. What the API returned is not.

- [`empty-content-reasoning-budget.md`](escalations/empty-content-reasoning-budget.md) — Crusoe's documented known issue that a small `max_tokens` on a reasoning model returns HTTP 200 with `message.content` `None`. Reproduced at `max_tokens=64`. The article's "raise to 1024" advice returned partial text that was still cut off (`finish_reason=length`).
- [`stale-or-wrong-inference-endpoint.md`](escalations/stale-or-wrong-inference-endpoint.md) — official 429-from-stale-endpoint and "404 page not found" troubleshooting, plus LiteLLM's legacy-host 403 report. This lab reproduced the missing-`/v1` 404 exactly, and confirmed the current official host does not WAF-block the published path-like prompt. It did **not** reproduce a 429 or a 403.

Redacted lab output: [`escalations/repro-results.json`](escalations/repro-results.json). Spend for that run was about $0.000237.

## License

MIT. See [LICENSE](LICENSE).
