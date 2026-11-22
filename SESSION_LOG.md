# Paid-session log: 21 November 2026

Attempt to execute [`PAID_SESSION_PLAN.md`](PAID_SESSION_PLAN.md) after an explicit go-ahead. Clock start: **7:18:45 PM PT** (America/Los_Angeles). Hard time box 90 minutes, teardown by T+70, spend cap $3, CPU-only, names prefixed `lab-esc-`.

**Result: the session stopped at authentication. No paid resources were created. Estimated cost: $0.00.**

Teardown verification is stated clearly below. Nothing `lab-esc-` exists in this sitting because no create command was ever issued.

## Timeline (America/Los_Angeles)

| Time PT | Event |
| --- | --- |
| 7:18:45 PM | Clock start. Crusoe CLI was not installed on the box. |
| 7:18–7:19 PM | Installed Crusoe CLI v1.1.0 and kubectl 1.32.3 from the official apt repository. |
| 7:19:09 PM | `CRUSOE_ACCESS_KEY_ID` and `CRUSOE_SECRET_KEY` were present in a fresh `bash -lc` (values never printed). `crusoe whoami` returned `Error: could not get identity: failed to authenticate user`. Feature-flag fetch was HTTP 401 Unauthorized. |
| 7:19 PM | Compared credential *shapes* only, never values. `CRUSOE_ACCESS_KEY_ID` is the **same string** as the existing Intelligence Foundry / Serverless Inference key (`CRUSOE_API_KEY`). `CRUSOE_SECRET_KEY` is a different, shorter value. Official CLI docs treat Cloud access-key/secret pairs and Intelligence API keys as distinct credentials (`crusoe config set inference_api_key` / `CRUSOE_INFERENCE_API_KEY` is a separate setting). |
| 7:20 PM | Wrote a 0600 TOML config under `/workspace/.crusoe-lab/config` (outside the git repo) from those env vars and retried with `CRUSOE_CONFIG_DIR`. `crusoe whoami` still returned 401 / failed to authenticate user. |
| 7:20:23 PM | Deleted `/workspace/.crusoe-lab` (config and CLI metadata). No `lab-esc-` create, list, or delete commands were run, because authentication never succeeded. |
| 7:21 PM | Session stopped. The three infrastructure issues remain documented, not reproduced. |

## Commands that ran (no resource creates)

```bash
# Install (no credentials involved)
sudo apt-get install crusoe kubectl
crusoe version   # v1.1.0

# Auth probes — both failed
crusoe whoami
# Error: could not get identity: failed to authenticate user
# also: failed to fetch feature flags ... 401 Unauthorized
```

A second `crusoe whoami` after writing the 0600 config produced the same error. `crusoe projects list`, `locations list`, `compute vms list`, and every create command in the plan were **not** run.

## What was supposed to be reproduced

1. Stopped VM with the 128 GiB OS disk still present (billable per public docs).
2. CMK Cluster Autoscaler unhealthy-pool state, CPU-only, best effort.
3. Load balancer backends `Online` while a client `curl`/`nc` times out, then a NodePort firewall rule as the fix.

None of these were attempted.

## Teardown verification — nothing lab-esc- remains

**Mandatory teardown result: no `lab-esc-` VM, disk, node pool, cluster, load balancer, firewall rule, VPC, or subnet was created in this sitting, so there was nothing to delete.**

Inventory list commands (`crusoe compute vms list`, `crusoe storage disks list`, `crusoe kubernetes clusters list`, `crusoe networking load-balancers list`, `crusoe networking vpc-firewall-rules list`, `crusoe networking vpc-subnets list`) could **not** be executed. The CLI could not authenticate to the Cloud API (HTTP 401). That is not the same as a successful empty inventory. It means this session has no Cloud API view of the account.

What can be stated with certainty:

- This session issued no `create`, `apply`, `start`, or `update --count` commands.
- The local 0600 CLI config was deleted.
- Spend for this sitting is $0.00.

If Cloud API keys are replaced with a working access key ID and secret (created in Crusoe Console under Security, not the Intelligence API key), the plan in `PAID_SESSION_PLAN.md` can be rerun, and the first step should still be a starting inventory plus a teardown grep for `lab-esc-`.

## Cost

Estimated cost of this sitting: **$0.00**. Hard cap was $3. No compute, disk, cluster, or load balancer was provisioned.

## Follow-up needed

Cloud API authentication must be fixed before any of the three infrastructure reproductions can run. The value currently in `CRUSOE_ACCESS_KEY_ID` is the Intelligence API key, which the Cloud CLI rejected. A Cloud access key ID and secret key pair need to be issued in the console and set in a fresh shell, without pasting the values into chat.
