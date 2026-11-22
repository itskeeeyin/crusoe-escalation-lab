# Example escalation: Serverless Fine-Tuning rejects a bad dataset

This is an example customer escalation built from a **public Crusoe Support FAQ** and a **real reproduction** on this account on 21 November 2026 at 7:09–7:10 PM PT (America/Los_Angeles). The customer name and any dollar impact below are **hypothetical**. The API evidence is not.

Suggested severity: **P2**, customer updates **daily**. The platform now rejects some bad files at upload, before a job or a GPU is created, and the error names the bad line. That is a blocked training launch, not a production inference outage. Promote to **P1** (updates every 4 hours) if a file that already matches the published `messages` schema is still rejected, or if a job hangs in `validating_files` instead of failing fast.

## Source (real public report)

Crusoe Support, "FAQ: Common dataset errors in Serverless Fine-Tuning," updated 30 September 2026:

https://support.crusoecloud.com/hc/en-us/articles/56536863886491-FAQ-Common-dataset-errors-in-Serverless-Fine-Tuning

The article opens with: "Most Serverless Fine-Tuning jobs that fail do so in the first few seconds, in `validating_files`, before a GPU is ever scheduled. The cause is almost always the training file, and the fix is almost always on your side."

On upload versus validation it still says: "Upload checks only the extension (`.jsonl` or `.parquet`), the 3 GB limit, and `purpose=fine-tune`. Content is checked when the job enters `validating_files`." A typical schema error is quoted as `Line doesn't contain 'messages' key: {'input': '...', 'output': ''}`.

This lab found that part of the FAQ is **stale**. On 21 November 2026, a `prompt`/`completion` JSONL and a trailing-comma JSONL were rejected at **upload** with HTTP 400, so no job was created. The error text is the same class of failure the FAQ describes; it just happens earlier than the article says.

Official API docs used for the calls: https://docs.crusoe.ai/managed-ai/serverless-fine-tuning/ and https://docs.crusoe.ai/api/managed-ai/. The documented base URL is `https://api.intelligence.crusoecloud.com` (not the inference host). Job create accepted the catalog id `model-meta-llama-llama-3-1-8b-instruct-2e441db2`; the HuggingFace-style name `meta-llama/Llama-3.1-8B-Instruct` returned HTTP 404 `Model 'meta-llama/Llama-3.1-8B-Instruct' not found`.

## Customer symptom

Hypothetical customer: a team exports support tickets as JSON or as OpenAI legacy `prompt`/`completion` rows, tries to upload the file, and either gets an immediate 400 or sees the upload succeed and the job fail shortly afterward. They open a ticket saying "fine-tuning is broken" or "the file uploaded, why did the job fail?"

## Reproduction evidence

Personal lab, this account, 7:09:30–7:10:48 PM PT, Intelligence Foundry API `https://api.intelligence.crusoecloud.com/v1`, cheapest 8B base model `meta-llama/Llama-3.1-8B-Instruct` (catalog id above, public training rate $0.40 per 1M tokens). Hard cap was $0.25. Intro credits only; no payment method was added. A corrected dataset was **not** submitted, because a passing file can leave `validating_files` and start training. Raw redacted calls are in `escalations/repro-results-finetune.json`. Uploaded files were deleted afterward (HTTP 200 `deleted: true`).

| Attempt | File | Upload | Job | Result |
| --- | --- | --- | --- | --- |
| Wrong schema (FAQ example) | `{"prompt": "...", "completion": "billing"}` | HTTP 400, `Invalid JSONL file: Line 1: missing required 'messages' key` | Not created | **Reproduced at upload**, earlier than the FAQ. |
| Trailing comma | Valid `messages` object with a trailing comma | HTTP 400, `Invalid JSONL file: Line 1: not valid JSON: trailing comma is not allowed: line 1 column 132 (char 131)` | Not created | **Reproduced at upload.** |
| No assistant turn | `messages` with only `system` and `user` | HTTP 200, 208 bytes, `purpose=fine-tune` | Created 7:10:33 PM PT; `validating_files` for ~7 seconds; then `queued` | Did **not** fail validation. Cancelled immediately at `queued`. `trained_tokens` stayed `null`. |
| Empty assistant content | `messages` with `assistant.content=""` | HTTP 200, 142 bytes | Not started (safety: the first uploaded file had already gone to `queued`) | Upload accepted. No job, so validation of this file was not observed. |

Job timeline for the no-assistant-turn file, all times PT:

- 7:10:33 PM — `POST /fine_tuning/jobs` with the catalog model id returned HTTP 200, `status=validating_files`, `trained_tokens=null`, `error=null`.
- 7:10:34–7:10:40 PM — retrieve still `validating_files`, `trained_tokens=null`.
- 7:10:41 PM — status became `queued`, `trained_tokens` still `null`. `POST /fine_tuning/jobs/{id}/cancel` returned HTTP 200, `status=cancelled`. A follow-up retrieve was already `cancelled`.

That matches the FAQ's later note that at validation time the platform mainly checks that each line is valid JSON with a `messages` key; a missing assistant turn can pass and only fail later (or train poorly). It does **not** match the FAQ's claim that upload ignores content.

Two price-estimate paths from the OpenAPI write-up were tried before create: `POST /v1/fine_tuning/jobs/price_estimate` returned HTTP 405, and `POST /v1/fine_tuning/price_estimate` returned HTTP 404. No estimate was used. The $0.25 cap was enforced by cancelling at `queued` and by not submitting a valid file.

## Hypotheses and tests

| ID | Hypothesis | Test | Result |
| --- | --- | --- | --- |
| H1 | The upload itself is rejected | Upload a `prompt`/`completion` JSONL with `purpose=fine-tune` | **Confirmed, and earlier than the FAQ.** HTTP 400, missing `messages` key. A trailing-comma file was also rejected at upload. |
| H2 | The file is valid JSON but not JSONL | Not needed; the first file was already one object per line, just the wrong schema | The 400 named the missing `messages` key, not a top-level array. |
| H3 | Rows use `prompt`/`completion` instead of `messages` | Same as H1 | **Confirmed** at upload, with a close cousin of the FAQ quote. |
| H4 | A file with `messages` but no assistant turn fails in `validating_files` | Upload (200), create a job, poll | **Rejected.** The job stayed in `validating_files` for ~7 seconds, then went to `queued` with `error=null`. Cancelled immediately. |
| H5 | This is a GPU or quota failure, not a dataset failure | Inspect `trained_tokens`, `error`, and how far the job got | The schema failures never created a job. The queued job had `trained_tokens` null and was cancelled before running. No billing or payment-method error was returned. |

## Workaround

- Treat HTTP 400 on `POST /v1/files` as a dataset problem when the body mentions `messages`, JSON, or a line number. A successful upload is no longer the only way this failure appears.
- Validate locally first with the companion procedure the FAQ points to ("Serverless Fine-Tuning job fails with dataset format or validation errors," Step 4). Map `prompt`/`completion`, Alpaca, and ShareGPT onto `messages` with `user` / `assistant` roles, and do not leave trailing commas.
- For job create, use the model id from `GET /v1/models?model_type=base_model` on `https://api.intelligence.crusoecloud.com/v1`. The HuggingFace-style name was not accepted in this run.
- If a job is created and leaves `validating_files` for `queued` or `running`, cancel immediately when the intent was only to test validation: `POST /v1/fine_tuning/jobs/{id}/cancel`.
- Delete rejected or leftover training files with `DELETE /v1/files/{id}`.

## Long-term fix and engineering ask

Practice recommendations, not a claim about Crusoe's roadmap:

- Update the FAQ sentence "Upload checks only the extension, the 3 GB limit, and `purpose=fine-tune`." Upload now also rejects a missing `messages` key and invalid JSON (trailing commas). Keep the `validating_files` path for checks that still happen after upload.
- Accept or document the catalog model id versus the HuggingFace-style name on job create, so a 404 `Model not found` is not mistaken for a missing fine-tuning offering.
- Publish the price-estimate path that the OpenAPI text describes, or remove it if it is not live (`/fine_tuning/jobs/price_estimate` was 405, `/fine_tuning/price_estimate` was 404 in this run).

## Customer updates (P2, daily)

Hypothetical comms. No real customer received these.

**Day 1:**

> We're looking at the fine-tuning failure. Some bad datasets are now rejected at upload with HTTP 400 (for example a missing `messages` key or invalid JSON). Other files still upload and are checked when the job is in `validating_files`. Please send the file ID or the 400 body, and if a job was created, the job ID and the `error` object. Next update tomorrow, or sooner if that error is in hand.

**Day 2:**

> In a reproduction, a `prompt`/`completion` JSONL was rejected at upload with `Invalid JSONL file: Line 1: missing required 'messages' key`, and a trailing comma was rejected as invalid JSON. That is a dataset problem, not a GPU or quota failure. Workaround: convert rows to chat-format JSONL with a `messages` array, re-upload, and create a new job. Crusoe's public FAQ still describes this failure as happening only in `validating_files`; the upload-time 400 is the current behavior we observed. Next update tomorrow, or sooner if a repaired file still fails.

**Day 3 (mitigated):**

> This is consistent with dataset validation, not with a platform outage. Please keep a local validator in the export pipeline. We're closing this P2 and asking docs to update the "upload only checks the extension" sentence. If a file that already matches the published `messages` schema is still rejected, or a job hangs in `validating_files`, we will reopen as a P1.

## Lessons

- "Upload succeeded" is no longer the only gate. Check the 400 body first.
- A missing `messages` key fails loudly at upload today; a missing assistant turn can still pass `validating_files` and reach `queued`. Do not use a "probably invalid" file as a safe way to avoid training spend — cancel if status becomes `queued` or `running`.
- Job create on this API wants the catalog model id, not only the public HuggingFace name.
- Delete training files when the test is done.

Spend for this reproduction: **$0.00**. No job reached `running`. `trained_tokens` stayed `null`. The cancelled job never reported a finish-time trained-token count. No payment method was added.
