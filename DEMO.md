# 5-minute live walkthrough

A practice script for walking someone through the empty-reply case: triage, then root cause, then a customer update. Times are a guide, not a clock. Use the evidence already in `results.json`, or rerun the lab if you want a live call. This is personal practice, not a Crusoe-internal demo.

Do not paste `CRUSOE_API_KEY` into the terminal history if you can avoid it, and never paste it into chat or a slide.

## Setup (30 seconds)

```bash
cd crusoe-escalation-lab
source .venv/bin/activate   # or: python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
export CRUSOE_API_KEY=...   # already in your shell if you are rerunning
```

Point at:

- This repo's README lab snapshot
- `results.json` → the `empty_reply` scenario
- Optional: the Page "Crusoe escalation practice lab"

What to say:

> This is a personal lab against my own Intelligence API account. The customer-facing symptom is "the API says success, but the agent returned a blank answer." I'm going to triage it the way I would on a P1, then show the root cause and the update I would send.

## 1. Triage (about 90 seconds)

If you want a live repro, run:

```bash
python practice_lab.py --skip-burst
```

The 21 November 2026 lab run finished in a few seconds. You can also skip the rerun and open the saved snapshot:

```bash
python - << 'PY'
import json
from pathlib import Path
data = json.loads(Path("results.json").read_text())
empty = next(s for s in data["scenarios"] if s["id"] == "empty_reply")
print(empty["issue"])
for attempt in empty["break_attempts"]:
    print(
        attempt["max_tokens"],
        attempt["status_code"],
        attempt["content"],
        attempt["finish_reason"],
        attempt["usage"],
    )
PY
```

Point at these fields, in this order:

1. HTTP status: `200`. This is not a 401, 404, 429, or 503, so it will not show up in a simple "error rate" board.
2. `message.content`: `null`.
3. `finish_reason`: `length`.
4. Usage: 49 prompt tokens, 64 completion tokens, and all 64 were `reasoning_tokens`.
5. Latency: 528 ms. The call was fast. The customer still got nothing.

What to say:

> First question: is the platform down, or is the response empty? The status is 200, so a health check that only looks at HTTP codes would stay green. The assistant message is null, finish_reason is length, and the entire token budget went to reasoning. That is enough to stop guessing about an outage and start testing the token budget and reasoning settings.

## 2. Root cause (about 2 minutes)

Point at the two fixes in `results.json` (or the README table):

| Attempt | Settings | Result |
| --- | --- | --- |
| Break | `reasoning_effort=high`, `max_tokens=64` | HTTP 200, `content` null, `finish_reason=length` |
| Fix A | `reasoning_effort=none`, `max_tokens=256` | Full one-sentence answer in 327 ms, 0 reasoning tokens |
| Fix B | `reasoning_effort=high`, `max_tokens=512` | Still empty. All 512 tokens were reasoning |

What to say:

> The model spent its token budget on a hidden reasoning trace and was cut off before the visible answer started. Raising `max_tokens` from 64 to 512 was not enough, because the new cap was still consumed by reasoning. Turning reasoning off with the same prompt produced a complete answer. If the product needs a reasoning trace, the cap has to cover the trace plus the answer, not just a slightly larger number.

> This is also what you would check after a model update: did default `reasoning_effort` change, or did the model start using more reasoning tokens for the same prompt, so a client cap that used to work now fails closed?

Related live evidence, if there is time: `openai/gpt-oss-120b` rejected `reasoning_effort=none` with HTTP 400, and with the parameter omitted and `max_tokens=32` it reproduced the same empty-reply pattern. That is in `healthcheck-output.txt`.

## 3. Customer update (about 90 seconds)

Point at the sample P1 update, and at the 4-hour cadence. Say it out loud, as you would send it:

> We're investigating chat completions that return HTTP 200 with an empty assistant message. Early evidence shows the model exhausting a low `max_tokens` budget on reasoning (`finish_reason=length`, `content` null) rather than a platform outage. Workaround: raise `max_tokens` enough to cover reasoning plus the answer, or set `reasoning_effort` to `none` or `low` if you do not need a reasoning trace. Next update in 4 hours, or sooner if we have a fix.

What to add, briefly:

- Who is affected: callers using a reasoning model with a tight `max_tokens`.
- What we ruled out: auth failures, unknown model IDs, 429/503, and malformed bodies. Those are separate, reproduced cases in this lab.
- When we would escalate to engineering: empty replies continue after a generous token cap and lower reasoning effort, or this starts happening at default settings that previously returned answers.

## If you have leftover time

- Run `python healthcheck.py` and point at the status table. It fails closed on empty content, not just HTTP errors.
- Skim `postmortems/P1-blank-agent-responses.md`. That write-up is labelled hypothetical; the reproduction inside it is this lab run.
