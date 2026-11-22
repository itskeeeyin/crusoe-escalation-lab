# Example escalation: Serverless Fine-Tuning fails in `validating_files`

This is an example customer escalation built from a **public Crusoe Support FAQ**. It is **documented, not reproduced**. This lab did not upload a training file or create a fine-tuning job, because that can schedule a GPU and is outside the cheap serverless-inference budget. The customer name and any dollar impact below are **hypothetical**.

Suggested severity: **P2**, customer updates **daily**. The job fails in the first few seconds, before a GPU is scheduled, and the platform returns an `error` object that usually quotes the bad line. That is a blocked training launch, not a production inference outage. Promote to **P1** (updates every 4 hours) if a file that already passed the published checks still fails in `validating_files`, or if jobs hang in that state instead of failing fast.

## Source (real public report)

Crusoe Support, "FAQ: Common dataset errors in Serverless Fine-Tuning," updated 30 September 2026:

https://support.crusoecloud.com/hc/en-us/articles/56536863886491-FAQ-Common-dataset-errors-in-Serverless-Fine-Tuning

The article opens with: "Most Serverless Fine-Tuning jobs that fail do so in the first few seconds, in `validating_files`, before a GPU is ever scheduled. The cause is almost always the training file, and the fix is almost always on your side."

On upload versus validation: "Upload checks only the extension (`.jsonl` or `.parquet`), the 3 GB limit, and `purpose=fine-tune`. Content is checked when the job enters `validating_files`. A fast failure with `trained_tokens: null` and `finished_at` close to `created_at` is a dataset failure, not a training failure." A typical schema error is quoted as `Line doesn't contain 'messages' key: {'input': '...', 'output': ''}`.

The same FAQ lists nine frequent mistakes (UTF-8 BOM, CRLF, trailing commas, `prompt`/`completion` rows, no assistant turn, blank lines, the role `human`, empty assistant replies, and literal newlines inside strings) and states that a job cannot be retried in place: "The Files API has no update operation and the Fine-tuning API has no retry... Upload the corrected file as a new file... and create a new job pointing at it."

## Customer symptom

Hypothetical customer: a team exports support tickets as JSON or as OpenAI legacy `prompt`/`completion` rows, uploads the file, and sees the upload succeed. The fine-tuning job then fails seconds later with an error on `training_file`. They open a ticket saying "fine-tuning is broken" or "the file uploaded, why did the job fail?"

## Reproduction status

**Documented, not reproduced.** No training file was uploaded and no fine-tuning job was created on this account. Evidence below is the public FAQ only.

## Hypotheses and tests

| ID | Hypothesis | Test | Result |
| --- | --- | --- | --- |
| H1 | The upload itself is rejected | Check the Files API response and that `purpose=fine-tune`, the extension, and the 3 GB cap | Not run here. The public FAQ says a successful upload only proves those three checks, not content. |
| H2 | The file is valid JSON but not JSONL (one array of examples) | Inspect the first bytes; run a local line-by-line `json.loads` | Not run here. The FAQ's tell is `line 1: top-level value must be an object, got list`. |
| H3 | Rows use `prompt`/`completion`, Alpaca, or ShareGPT instead of `messages` | Search for a `messages` key; look at the job `error` object | Not run here. The FAQ quotes `Line doesn't contain 'messages' key` for this shape. |
| H4 | Hidden byte problems (BOM, CRLF, a literal newline in a ticket body) | `file train.jsonl`, `head -c 3 \| xxd`, then rewrite with `encoding='utf-8'` and `newline='\n'` | Not run here. The FAQ calls an unescaped newline in support text "the single most common failure in datasets built from real support text." |
| H5 | This is a GPU or quota failure, not a dataset failure | Compare `created_at` and `finished_at`, and check `trained_tokens` | Not run here. The FAQ says a fast fail with `trained_tokens: null` is a dataset failure. |

## Workaround

- Do not treat a successful upload as a valid dataset. Validate locally first with the companion procedure the FAQ points to ("Serverless Fine-Tuning job fails with dataset format or validation errors," Step 4).
- Normalize bytes (strip BOM, CRLF to LF, drop blank lines), then make every line parse, then map `prompt`/`completion`, Alpaca, and ShareGPT onto `messages` with `user` / `assistant` roles.
- Upload the repaired file as a **new** file and create a **new** job. The same job cannot be retried. Delete the rejected file afterwards.
- If the local validator passes and the job still fails, re-download the uploaded file with `GET /v1/files/<id>/content` and validate that copy; the FAQ lists a mismatched local file, overlong rows, and rows over roughly 100 KB as the next checks.

## Long-term fix and engineering ask

Practice recommendations, not a claim about Crusoe's roadmap:

- Surface the dataset `error` line in the Console next to the job, not only on the retrieve API, so the first ticket does not have to ask "where is the error?"
- Reject or warn at upload time when the first line is a JSON array, or when no `messages` key is present, instead of waiting for `validating_files`.
- Keep the local validator and the platform checks aligned, including role names such as `human` / `gpt` that the FAQ says can slip past validation and only fail at tokenization.

## Customer updates (P2, daily)

Hypothetical comms. No real customer received these.

**Day 1:**

> We're looking at the fine-tuning job that failed shortly after upload. A successful file upload only checks the extension, size, and purpose; content is checked when the job enters `validating_files`. A fast failure with `trained_tokens` null is usually a dataset problem, not a GPU or quota failure. Please send the job ID, file ID, model ID, and the `error` object from the job. Next update tomorrow, or sooner if that error is in hand.

**Day 2:**

> Crusoe's public fine-tuning FAQ lists this exact shape: upload succeeds, then the job fails in `validating_files` because the file is not chat-format JSONL (for example a JSON array, or `prompt`/`completion` rows). Workaround: repair the file, upload it under a new file ID, and create a new job — the original job cannot be retried. Next update tomorrow, or sooner if a repaired file still fails.

**Day 3 (mitigated):**

> This is consistent with a dataset validation failure, not with a platform outage. Please keep the local validator in the export pipeline so the next upload is checked before a job is created. We're closing this P2. If a file that already matches the published `messages` schema still fails, or a job hangs in `validating_files`, we will reopen as a P1.

## Lessons

- "Upload succeeded" is not "the dataset is valid." Say that in the first customer update.
- Failures that happen before a GPU is scheduled should not be triaged as capacity, quota, or engine bugs until the `error` object is read.
- The job has no retry. Plan the workaround around a new file ID and a new job from the start.

No lab spend. This issue was not reproduced.
