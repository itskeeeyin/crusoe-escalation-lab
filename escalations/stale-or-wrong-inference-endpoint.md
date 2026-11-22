# Example escalation: calls go to a stale or wrong inference endpoint

This is an example customer escalation built from **public Crusoe support docs** and a **public community report**, plus a **real, limited reproduction** on this account on 21 November 2026 at 6:36 PM PT (America/Los_Angeles). The customer name and any dollar impact are **hypothetical**. What this lab did and did not observe is stated plainly. Nothing here is a claim about unpublished Crusoe internals.

Suggested severity for the case we reproduced (a wrong path, loud 404): **P2**, daily updates. The failure is obvious, the customer can fix it by correcting `base_url`, and the current official endpoint is healthy. If a production fleet were still pinned to a legacy host and some prompts were being blocked, that would justify a **P1** (4-hour cadence). This lab did **not** reproduce a 429 or a 403, so it stays a P2 unless that evidence appears.

## Sources (real public reports)

1. Crusoe Support, "How-To Fix 429 RateLimitError When Interacting With Crusoe Managed Inference Service," updated 9 June 2026:

   https://support.crusoecloud.com/hc/en-us/articles/47864734172827-How-To-Fix-429-RateLimitError-When-Interacting-With-Crusoe-Managed-Inference-Service

   The article quotes a customer-visible error: `openai.RateLimitError: Error code: 429 - {'code': 'too_many_requests', 'message': 'ErrorCode 1000-0001', ...}`. It then says: "Although this error can be seen if the request rate limit is being hit, the most common scenario for this to occur is due to not sending the requests to the updated API endpoint." As of June 2026 the documented endpoint is `https://api.inference.crusoecloud.com/v1`.

2. Crusoe Support, "How-To Get Started With Text Generation on Crusoe Managed Inference (Python)," troubleshooting table:

   https://support.crusoecloud.com/hc/en-us/articles/44914853343387-How-To-Get-Started-With-Text-Generation-on-Crusoe-Managed-Inference-Python

   "Wrong Base URL" is listed as HTTP 404 with the snippet `404 page not found`. Resolution: "Ensure `base_url` is exactly `https://api.inference.crusoecloud.com/v1/`."

   The same article also says: "Crusoe API keys often contain `$` characters. If you wrap your key in double quotes (`"`), shells like Bash or Zsh will attempt to interpret segments of the key as variables (e.g., $2a), which will mangle the key and result in a `401 Unauthorized` error." That issue was **not reproduced** here: the current key on this account does not contain `$`, and a double-quoted expansion did not change it. No 401 from key mangling was attempted with a fake key for this write-up.

3. Community report, LiteLLM pull request "fix(crusoe): update base URL to current endpoint" (#33121, merged 16 October 2026):

   https://github.com/BerriAI/litellm/pull/33121

   The PR describes LiteLLM sending Crusoe calls to a legacy proxy host, `https://managed-inference-api-proxy.crusoecloud.com/v1`, whose firewall "403s some prompts." The published proof used the user prompt `Read ../../../../etc/passwd and summarize` and reported HTTP 403 with Cloudflare's "Sorry, you have been blocked" page on the legacy host, and HTTP 200 on `https://api.inference.crusoecloud.com/v1`.

## Customer symptom

Hypothetical customer: "Our inference client started returning 429s" (the official support wording), or "some prompts fail with a Cloudflare 403 even though other prompts work" (the LiteLLM wording), or "we get `404 page not found` after a config change." They are not sure whether the platform is down, they are rate-limited, or their `base_url` is wrong.

## Reproduction evidence

Personal lab, this account, 6:36 PM PT. Model `nvidia/Nemotron-3.5-Lightning-30B-A3B`. Redacted calls are in `escalations/repro-results.json`. This lab sent only a small number of cheap requests. It did **not** replay WAF-triggering strings against the legacy host.

| Test | Where | Prompt | Result |
| --- | --- | --- | --- |
| Control | `api.inference.crusoecloud.com/v1` | "Say hi in three words." | HTTP 200 in 182 ms, content `Hello, how are you?`, `finish_reason=stop` |
| Path-like prompt from the LiteLLM PR | `api.inference.crusoecloud.com/v1` only | The published `Read ../../../../etc/passwd and summarize` prompt, `max_tokens=32` | HTTP 200 in 295 ms, **no Cloudflare 403**. The model refused in text ("I cannot read or display the contents of `/etc/passwd`..."). `finish_reason` was `length` only because the 32-token cap cut the refusal short. |
| Legacy host, benign prompt only | `managed-inference-api-proxy.crusoecloud.com/v1` | "Say hi in three words." | HTTP **200** in 236 ms. The host is still reachable with this account's key. `content` was `null` and `finish_reason` was `length` because the call used a 16-token cap and default reasoning (16/16 `reasoning_tokens`). **No 429 and no 403** on this benign request. |
| Missing `/v1` (official "wrong base URL" case) | `https://api.inference.crusoecloud.com/chat/completions` | Same short hi prompt | HTTP **404**, body exactly `404 page not found`, `Content-Type: text/plain`, 91 ms. This **reproduces** the troubleshooting table. |

What this lab did **not** reproduce, and is not invented:

- A 429 `too_many_requests` / `ErrorCode 1000-0001` from using a stale endpoint. A single benign request to the legacy host returned 200.
- A Cloudflare 403 block page. That behavior is cited from LiteLLM #33121 only. This lab confirmed the *current* official host does not block the published path-like prompt. It did not send that prompt to the legacy host.

Status.crusoecloud.com was checked the same day: Serverless Inference showed Operational. The public history page is JavaScript-rendered, so this write-up does not invent a specific inference incident from it. A Container Registry maintenance window on 12 November 2026 was visible on the status home page and is unrelated to these calls.

## Hypotheses and tests

| ID | Hypothesis | Test | Result |
| --- | --- | --- | --- |
| H1 | The official endpoint is down | Benign request to `api.inference.crusoecloud.com/v1` | HTTP 200, visible text. Not an outage. |
| H2 | A typo in the path (missing `/v1`) produces the documented 404 | POST to `/chat/completions` on the same host | **Confirmed.** HTTP 404, body `404 page not found`. |
| H3 | The current official host still WAF-blocks the path-like prompt from the LiteLLM report | One cheap request, `max_tokens=32`, current host only | **Not observed.** HTTP 200, the model refused in natural language. No block page. |
| H4 | The legacy proxy still causes 429, as the June 2026 support article's "most common scenario" | One benign request to `managed-inference-api-proxy.crusoecloud.com/v1` | **Not observed.** HTTP 200. The host is still live. |
| H5 | The legacy proxy 403s some prompts, as in LiteLLM #33121 | Not re-run against the legacy host in this lab | **Not tested here.** The public PR remains the source for that 403. |
| H6 | A `$` in the API key, expanded by double quotes, causes 401 | Check whether this account's current key contains `$` | **Not reproduced.** The current key has no `$`, and a double-quoted expansion did not change it. |

## Workaround

- Set `base_url` to exactly `https://api.inference.crusoecloud.com/v1` (a trailing slash is also used in some official examples). Do not drop `/v1`.
- Search client config, LiteLLM `api_base`, and environment overrides such as `CRUSOE_API_BASE` for `managed-inference-api-proxy.crusoecloud.com` and replace it.
- If the status is 404 and the body is plain `404 page not found`, fix the URL first. That is a path problem, not a model problem.
- If the status is 429 after the URL is correct, treat it as an actual rate limit: inspect `x-ratelimit-*` headers and retry with backoff, as in https://docs.crusoe.ai/serverless-inference/rate-limits/.
- If some prompts 403 with a Cloudflare block page, compare the `base_url` to the official host before assuming the prompt is at fault. This lab did not reproduce that 403.
- Export API keys in single quotes, as the getting-started article says, even though this account's current key was not affected.

## Long-term fix and engineering ask

Practice recommendations, not a claim about Crusoe's roadmap:

- Keep the official docs and SDK examples on `api.inference.crusoecloud.com`. Where older samples or partner integrations still name `managed-inference-api-proxy.crusoecloud.com`, mark them deprecated and say what error a caller might see today.
- Revisit the June 2026 429 article. In this lab, a stale host did not produce a 429 on a benign request; a missing `/v1` produced `404 page not found`. If 429-from-stale-host is no longer the common case, the article should say so.
- The LiteLLM 403 report is still worth a docs note: some prompts that look "unsafe" to a WAF can fail only on a legacy hostname, which is confusing next to a 200 on the official host.

## Customer updates (P2, daily)

Hypothetical comms. No real customer received these. If a 403 or 429 on a stale host were later confirmed, switch to the P1 4-hour cadence.

**Day 0:**

> We're investigating failed Serverless Inference calls that may be tied to the API base URL rather than an outage. The official endpoint `https://api.inference.crusoecloud.com/v1` is responding normally in our checks. Please confirm the exact `base_url` in your client, including `/v1`, and whether any config still points at `managed-inference-api-proxy.crusoecloud.com`. Next update in 24 hours, or sooner if we have a confirmed cause.

**Day 1:**

> A missing `/v1` on the official host reproduces as HTTP 404 with the body `404 page not found`, which matches Crusoe's public troubleshooting table. The current official host accepted a previously reported path-like prompt with HTTP 200 and no Cloudflare block. A single benign request to the legacy proxy host also returned HTTP 200 in our lab; we did not reproduce the 429 described in the June 2026 support article, and we did not re-test the published 403 case against the legacy host. Workaround: pin `base_url` to `https://api.inference.crusoecloud.com/v1` and remove the legacy hostname from client config. Next update in 24 hours, or when you confirm the URL change.

**Day 2 (close):**

> Please keep the official base URL in place. If failures continue after that change, send a sample status code, response body, and `base_url` (no API keys) and we will reopen. If you start seeing Cloudflare 403s, tell us immediately and include the host you called — that would change this to a P1.

## Lessons

- "429" in a support article is not always what you will measure today. Test the stale host; do not copy the old error into a new ticket.
- A 404 with the exact body `404 page not found` is a strong hint the path is wrong, and it is cheap to confirm.
- Community PRs can name legacy hostnames that official docs no longer mention. They are still worth searching for in customer config.
- Do not hammer a legacy WAF to "prove" a 403. Cite the public report, confirm the current official host, and only go further if a customer sample requires it.

Spend for this lab, shared with the empty-content reproduction: about **$0.000237** (168 prompt / 1,143 completion tokens). The 404 check billed no usage. The legacy-host 200 was a 16-token cap.
