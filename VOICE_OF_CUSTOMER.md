# Voice of the customer

Friction observed while setting up and calling Crusoe Serverless Inference as a new user on this account, written as engineering or docs feedback tickets. Each item is something actually seen in public docs or in live API responses from 21 November 2026 (America/Los_Angeles). This is personal lab feedback, not a Crusoe-internal ticket queue, and it does not claim hidden platform behavior.

Severity here is a practice label for triage discussion: **High** for silent user-visible failure, **Medium** for a mismatch that blocks or misleads a new user, **Low** for docs or error-shape polish.

## VOC-1. Signup docs disagree on whether a payment method is required for intro credits

- **Severity:** Medium (docs)
- **Where it showed up:** While creating an account and deciding whether a card was required before trying Serverless Inference.
- **What the docs say:**
  - [Create an account](https://docs.crusoe.ai/create-an-account.md) opens with "Create an account and add billing information to start using Crusoe Cloud." After email verification it tells you to skip to Enable billing. Section 3, Enable billing, says: "To provision resources or use the managed inference service, you must enable billing on your account. You will need a valid, non-prepaid credit card to proceed."
  - The [August 2026 updates](https://docs.crusoe.ai/updates/2026/august/) entry from 19 August 2026 (000108, Introductory Credits) says: "New and existing users will receive credits they can use in the Intelligence Foundry to try out Serverless Inference and Serverless Fine-Tuning—without adding a payment method."
- **Why it matters:** A new user can reasonably conclude they must add a card before they can try inference, or that the two pages describe different products. The updates page is the one that describes intro credits without a payment method.
- **Suggested fix:** Update the create-an-account page so billing is split in two: introductory Intelligence Foundry credits for Serverless Inference and Serverless Fine-Tuning do not require a payment method, per the 19 August 2026 update; provisioning infrastructure or staying on paid usage after credits are exhausted does. Link the two pages to each other so the getting-started path matches the changelog.

## VOC-2. HTTP 200 with null content when reasoning exhausts max_tokens

- **Severity:** High (API / developer experience)
- **Where it showed up:** Lab scenario `empty_reply` in `results.json`, 5:13 PM PT.
- **What we saw:** `nvidia/Nemotron-3.5-Lightning-30B-A3B` with `reasoning_effort=high` and `max_tokens=64` returned HTTP 200 in 528 ms. `message.content` was null, `finish_reason` was `length`, and all 64 completion tokens were `reasoning_tokens`. A reasoning trace was present and had been cut off mid-thought.
- **Why it matters:** A customer agent can look "up" on any monitor that only checks HTTP status, while users get a blank answer. This is the shape a P1 will actually take, and it is easy to mis-triage as a client bug or an outage.
- **Suggested fix:** Document that `max_tokens` includes reasoning tokens, and that `finish_reason=length` plus empty `content` means the budget ran out during reasoning. Consider a warning in the response, or official client guidance to treat empty `content` on HTTP 200 as a failure. A synthetic monitor should assert non-empty content, not only status codes.

## VOC-3. Raising max_tokens alone did not fix the empty reply; disabling reasoning did

- **Severity:** Medium (docs / developer experience)
- **Where it showed up:** Same lab run, fix attempts in `results.json`.
- **What we saw:** `reasoning_effort=none` with `max_tokens=256` returned a full one-sentence answer in 327 ms, `finish_reason=stop`, 0 reasoning tokens. The same prompt with `reasoning_effort=high` and `max_tokens=512` still returned empty content; all 512 completion tokens were reasoning, `finish_reason=length`.
- **Why it matters:** The obvious first workaround, "just raise the cap a bit," can fail. A support article that only says "increase `max_tokens`" will send people in a circle.
- **Suggested fix:** Document both levers: lower or disable `reasoning_effort` when a trace is not required, and if a trace is required, size `max_tokens` for reasoning plus the answer. Include a worked example where a higher cap is still not enough.

## VOC-4. gpt-oss-120b rejects reasoning_effort=none, and a tight cap then goes blank

- **Severity:** High (API / developer experience)
- **Where it showed up:** Live `healthcheck.py` runs at 5:28:43 PM and 5:29:11 PM PT, captured in `healthcheck-output.txt`.
- **What we saw:**
  1. `openai/gpt-oss-120b` with `reasoning_effort=none` returned HTTP 400 in 148 ms: `BadRequestError 400 Harmony does not support reasoning_effort='none' (parameter=reasoning_effort)`.
  2. Retrying the same short prompt with the parameter omitted and `max_tokens=32` returned HTTP 200, `content` null, `finish_reason=length` — the same empty-reply shape as VOC-2.
  3. Retrying again with the parameter omitted and `max_tokens=256` returned `ready` with `finish_reason=stop` in 296 ms.
- **Why it matters:** A client cannot "turn off reasoning" on this model with the parameter that works on Nemotron 3.5 Lightning. If the client still sends a tight cap, the call looks successful and returns nothing. Blindly forwarding `reasoning_effort` to every catalog model will 400.
- **Suggested fix:** Publish which models accept `reasoning_effort` (the `/v1/models` `supported_parameters` field described in [this support article](https://support.crusoecloud.com/hc/en-us/articles/55002524169499-How-To-List-Model-Features-via-curl-and-the-Inference-API) is the right hook). Reject unknown parameters with a message that names a supported alternative. Document that default reasoning on models like `gpt-oss-120b` still needs a cap large enough for the trace plus the answer.

## VOC-5. Public rate-limit header table is missing headers the API actually sends

- **Severity:** Low (docs)
- **Where it showed up:** Lab burst and later healthcheck responses, 5:13 PM PT.
- **What we saw:** Responses included the four headers listed in [Serverless rate limits](https://docs.crusoe.ai/serverless-inference/rate-limits/): `x-ratelimit-limit-tokens`, `x-ratelimit-remaining-tokens`, `x-ratelimit-limit-requests`, and `x-ratelimit-remaining-requests`. They also included `x-ratelimit-limit-output-tokens` and `x-ratelimit-remaining-output-tokens` (observed value: 200,000). This account's request and token caps were 600 RPM and 2,000,000 TPM, which match the documented defaults when a payment method is on file. A 25-request burst did not return HTTP 429, and this write-up does not invent one.
- **Suggested fix:** Add the output-token headers to the public table, with the same style of example values and a one-line description.

## VOC-6. A typo and a retired model ID return the same 404 shape

- **Severity:** Low (API / developer experience)
- **Where it showed up:** Lab scenario `wrong_model`.
- **What we saw:** `nvidia/Nemotron-3.5-Lightning-30B` (missing `-A3B`) and `nvidia/Nemotron-3-Nano` (a retired name; deprecations are listed in [Crusoe Updates: 2026](https://docs.crusoe.ai/updates/2026/)) both returned HTTP 404 with `code: model_not_found` and `Model not found: <id>`.
- **Why it matters:** The status code cannot tell a customer "you typo'd the ID" from "this model was deprecated." They have to compare the string to `GET /v1/models` and to the changelog themselves.
- **Suggested fix:** Keep `model_not_found` for unknown IDs, and add a distinct `code` or message when the ID was previously served and is now retired, plus a link to the current catalog or the deprecation note.

## VOC-7. 401 bodies do not use the same error object as 400s

- **Severity:** Low (docs / SDK)
- **Where it showed up:** Lab scenario `auth_failure`.
- **What we saw:** A fake key returned HTTP 401 in 84 ms with `{"errors": ["Authentication failed"], "id": "..."}`. A missing `Authorization` header returned HTTP 401 in 110 ms with `{"errors": ["Authentication failed"]}`. Malformed chat bodies, by contrast, returned HTTP 400 with an OpenAI-style `error` object (`type`, `message`, `code`).
- **Why it matters:** A client that only parses `error.message` will mishandle 401s. After a key rotation, that makes a simple auth miss look like an unknown failure.
- **Suggested fix:** Document the 401 body, or align it with the `error` object used on 400s, and mention the shape in the getting-started guide: https://docs.crusoe.ai/quickstart/getting-started-with-serverless-inference/

## VOC-8. Email verification codes expire in five minutes

- **Severity:** Low (docs already describe this; still felt tight in practice)
- **Where it showed up:** Email signup, before the first inference call. The behavior matches the create-an-account page: each code expires five minutes after it is sent, and five incorrect entries invalidate it.
- **Why it matters:** If the code lands in a mailbox that is not the browser you are using to sign up, five minutes is a short window. The friction is real even though the docs are accurate.
- **Suggested fix:** Keep the security behavior if it is intentional, and put the expiry more prominently on the verification screen itself, not only in the documentation. A slightly longer expiry, or an automatic resend, would reduce signup retries.
