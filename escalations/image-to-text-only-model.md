# Example escalation: image request to a text-only Serverless model returns HTTP 400

This is an example customer escalation built from a **public Crusoe known-issue warning** and a **real reproduction** on this account on 21 November 2026 at 6:58 PM PT (America/Los_Angeles). The customer name and any dollar impact below are **hypothetical**. The API evidence is not.

Suggested severity: **P2**, customer updates **daily**. In this run the API failed loudly: HTTP 400 with `unsupported multimodal content: image_url`. That is a broken client path, but it is visible in error rates and has a clear workaround (use a multimodal model, or drop the image). Promote to **P1** (updates every 4 hours) if the same request returns HTTP 200 and a fluent answer that ignored the image — the silent path in the same public warning — because monitors stay green while answers are wrong.

## Source (real public report)

Crusoe Support, "LLM Capabilities - Image / Text / Browser Control in MI," updated 30 September 2026:

https://support.crusoecloud.com/hc/en-us/articles/56524456657947-LLM-Capabilities-Image-Text-Browser-Control-in-MI

The article warns: "Sending an image to a text-only model does not fail gracefully. Depending on the model you get a `400` about unsupported content, or the model silently ignores the image and answers from the text alone — which looks like a working request returning nonsense. Confirm `modality` is `multimodal` in Step 1 first."

It also says image input is a per-model property, not an endpoint property, and tells callers to check `architecture.modality` on `GET /v1/models` (`text` versus `multimodal`) before sending an `image_url` part. Models tagged `image text to text` at the time of the article include Nemotron 3 Nano Omni, Gemma 4 31B, Kimi K2.6, GLM-5.3 Flash, and Qwen3.8 27B.

## Customer symptom

Hypothetical customer: an app or agent always attaches a screenshot or a data-URI image to chat completions. After they point the same client at a cheaper text-only Serverless model, every request fails with HTTP 400, or (on the other documented path) succeeds with an answer that does not mention the image. They open a ticket: "vision is broken on Serverless" or "the model is ignoring our screenshot."

## Reproduction evidence

Personal lab, this account, 6:58:47 PM PT, model `nvidia/Nemotron-3.5-Lightning-30B-A3B`, base URL `https://api.inference.crusoecloud.com/v1`. The image was a 1×1 PNG data URI so spend stayed tiny. Raw redacted calls are in `escalations/repro-results-batch2.json`.

| Check | What was sent | HTTP | Result |
| --- | --- | --- | --- |
| Image to a text-only model | `reasoning_effort=none`, `max_tokens=32`, user content = text "What color is this image? Reply in one word." plus `image_url` data URI | 400 in 265 ms | `invalid_request_error`: `unsupported multimodal content: image_url`. No usage was billed. |
| Catalog check, same account | `GET /v1/models` | 200 | Lightning: `architecture.modality=text`, tags `text to text`. Nemotron 3 Nano Omni and Gemma 4 31B: `modality=multimodal`, tags include `image text to text`. |

This is the loud 400 path in the public warning, not the silent-ignore path. The silent path was **not** observed on Lightning in this run.

A side check in the same script sent two consecutive `user` messages with no image, because the official getting-started troubleshooting table documents that as HTTP 400 "Conversation roles must alternate...". On Lightning that call returned **HTTP 200** with content `Hello! Yes, I am here.` (26 prompt / 8 completion tokens, `finish_reason=length` because the cap was 8). That is an observation about one model, not a fifth write-up, and it is recorded in the same results file.

## Hypotheses and tests

| ID | Hypothesis | Test | Result |
| --- | --- | --- | --- |
| H1 | The API or key is bad | Same host, later text-only call in the same script | The consecutive-role text call on the same host returned HTTP 200. The image call's 400 is not an outage. |
| H2 | The model ID is not in the catalog | `GET /v1/models` | Lightning is listed. The 400 names `image_url`, not `model_not_found`. |
| H3 | Lightning is multimodal and this is a platform regression | Read `architecture.modality` and tags | **Rejected.** Lightning is `text` / `text to text`. Omni and Gemma 4 31B are `multimodal` / `image text to text`. |
| H4 | A text-only model rejects `image_url` with HTTP 400 about unsupported content, as documented | Send a 1×1 PNG data URI plus a one-word prompt | **Confirmed.** HTTP 400, `unsupported multimodal content: image_url`. |
| H5 | This model silently ignores the image and answers from the text (the other documented path) | Inspect status and whether content answers the color question | **Not observed** on Lightning. The call never reached an assistant message. |

## Workaround

- Before sending `image_url`, check `GET /v1/models` and only use IDs whose `architecture.modality` is `multimodal` (or whose tags include `image text to text`).
- If the product only needs text, strip image parts in the client when the chosen model is text-only, so a model swap does not turn into a 400 wave.
- If the product needs the pixels, switch to a currently listed multimodal Serverless model (in this catalog check: Nemotron 3 Nano Omni or Gemma 4 31B, among others). Do not assume the chat-completions endpoint itself accepts images for every model.
- Treat HTTP 200 answers to image questions on a `modality=text` model as a client bug if they ever appear; that is the silent path in the public warning.

## Long-term fix and engineering ask

Practice recommendations, not a claim about Crusoe's roadmap:

- Keep the 400 on text-only models. A loud rejection is better than the silent-ignore path described in the same article.
- Include the chosen model ID and its `architecture.modality` in the 400 message, so the first ticket is not "is vision down?"
- In the Console model picker, hide or warn when a client that has been sending images is pointed at a `text` model.

## Customer updates (P2, daily)

Hypothetical comms. No real customer received these.

**Day 1:**

> We're investigating HTTP 400 responses on image questions to Serverless Inference. Early evidence points to an `image_url` being sent to a text-only model, not to an endpoint outage. Please send the model ID, a redacted request body, and the 400 message. Next update tomorrow, or sooner if we confirm the modality mismatch.

**Day 2:**

> This matches Crusoe's public warning: sending an image to a text-only model can return a 400 about unsupported content. In a reproduction on `nvidia/Nemotron-3.5-Lightning-30B-A3B`, which the catalog lists as `architecture.modality=text`, a 1×1 PNG data URI returned HTTP 400 `unsupported multimodal content: image_url` in 265 ms. Workaround: check `GET /v1/models` and send images only to `multimodal` IDs, or drop the image part for text-only models. Next update tomorrow, or sooner if you confirm the client change.

**Day 3 (mitigated):**

> The 400s are consistent with a text-only model receiving `image_url`, not with a vision outage. Please keep the modality check in the client. We're closing this P2. If a model whose catalog entry is `multimodal` starts returning this 400, or a text-only model starts answering image questions with HTTP 200 and no error, we will reopen as a P1.

## Lessons

- Image input is a property of the model, not of `https://api.inference.crusoecloud.com/v1`. Confirm `architecture.modality` before blaming the endpoint.
- A 400 that names `image_url` is a gift for triage. The worse case in the same public article is HTTP 200 with a confident, image-free answer.
- A 1×1 PNG is enough to classify the failure and keeps spend at zero for the 400 itself.

Spend for this reproduction: about **$0.000003** (26 prompt / 8 completion tokens on the text-only side check). The 400 itself reported no usage.
