# Interview questions

Questions I would actually want answered as a Senior Escalation Manager, grouped by public product area. They are meant to test how work flows when something is broken, not to collect marketing points. This is personal interview prep. It does not claim to be a Crusoe-internal brief, and it does not assume unpublished product behavior.

## Intelligence Foundry and Serverless Inference

- When a customer says "the API is up but we get no answer," what do you want in the first ticket: HTTP status only, or `content`, `finish_reason`, and `reasoning_tokens` as well? Who owns that standard?
- How do you tell a client `max_tokens` / `reasoning_effort` issue from a model regression, when both can look like HTTP 200?
- `reasoning_effort=none` is accepted on some models and rejected on others. In this lab, `nvidia/Nemotron-3.5-Lightning-30B-A3B` accepted it and `openai/gpt-oss-120b` returned HTTP 400 (`Harmony does not support reasoning_effort='none'`). Is `supported_parameters` on `GET /v1/models` the official source of truth, and do customers get pointed there before they open a ticket?
- What does a model deprecation look like for a customer who is still sending the old ID? In this lab a typo and a retired name both returned HTTP 404 `model_not_found`. Is that the intended long-term shape, or is a dedicated deprecation code planned?
- When should a customer move from Serverless Inference to Self-Serve Deployments? What symptoms (latency, 503s, rate-limit pressure, reserved capacity) should make an escalation manager raise that, rather than only asking for a higher RPM?
- Public rate-limit docs describe 429 as "you exceeded TPM or RPM" and 503 as "you are within limits, the shared endpoint is busy," and they list four `x-ratelimit-*` headers. This lab also saw `x-ratelimit-limit-output-tokens` and `x-ratelimit-remaining-output-tokens`. Which headers should customers be told to log, and who owns keeping the public table current?
- How much notice do customers get before a model is removed from Serverless Inference, and where is that promised? The changelog at https://docs.crusoe.ai/updates/2026/ is public; is that the contract, or is there also a direct notice path?
- After a customer rotates an Intelligence API key, what failure shape should they expect, and how quickly should a "known-good key still returns 401" case be escalated?

## Crusoe Managed Kubernetes (CMK)

Docs: https://docs.crusoe.ai/orchestration/cmk/overview.md

- When a training or inference workload on CMK is "down," how do you split control plane, node pool, add-on (GPU operator, network operator, CSI), and AutoClusters remediation in the first 15 minutes?
- AutoClusters is described as automatically detecting and resolving common hardware failures. What does the customer still need to do, and what should they see in the console or tickets while remediation is running?
- A customer says GPUs are attached but not schedulable. What is the default evidence pack (node conditions, operator logs, instance type, driver add-on version), and which of those can support collect without jumping into the customer's cluster?
- CMK is billed at a published $0.10 per cluster-hour, plus the underlying instances. Have billing surprises (a cluster left running, a node pool that did not scale in) shown up as escalations, and who owns the explanation?
- How do you handle a ticket that is really an application bug in the customer's GPU operator settings, versus a ticket that is a Crusoe-managed control plane issue, without bouncing the customer?

## GPU and CPU virtual machines

Docs: https://docs.crusoe.ai/infrastructure-cloud/overview.md

- A multi-node job hangs. How do you decide, from the first description, whether to start with the instance, the interconnect (InfiniBand, NVLink, or Ethernet on L40S), the image, or the customer's framework?
- What is the usual customer-visible difference between on-demand, spot, and reserved capacity when an escalation is about "I cannot launch the instance type I launched yesterday"?
- For GPU VMs, which failures are expected to be host-level (and therefore Crusoe-owned) versus in-guest (and therefore a shared debug)?
- When is "try a different location" an acceptable mitigation, and when does that hide a regional problem that should stay open as a P1?

## Managed Slurm

Docs: https://docs.crusoe.ai/orchestration/slurm/overview.md

- Managed Slurm can be created as a fully managed cluster or as a CMK add-on. Do those two paths fail differently from the customer's point of view, and do they share one escalation queue?
- A job sits in queue. How do you distinguish node-set capacity, topology-aware placement, a login-node problem, and a user or account mapping issue?
- Shared storage is mounted at `/home` across login and worker nodes. If a job can start but cannot write checkpoints, what is the first split between that shared volume, a persistent disk, and regional object storage?
- L40S node sets are documented as PCIe without InfiniBand. Have NCCL or multi-node jobs on L40S produced a repeating ticket pattern, and is that called out early in triage so people do not debug it as an InfiniBand failure?

## Storage

Docs: https://docs.crusoe.ai/storage/disks/overview.md and https://docs.crusoe.ai/storage/object-storage/overview/

- Ephemeral disks are documented as erased on stop, restart, or host failure, and as suitable only when data loss is tolerable. How often do escalations start as "my data is gone" on an ephemeral volume, and what is the first sentence you want in the docs or the console to prevent that?
- Persistent disks cannot be resized while attached, and they must be unmounted before detach. Which of those operational limits generates the most severity-raising tickets, and can the API or console fail more clearly?
- Object storage is regional, S3-compatible, and uses a different key than the Intelligence API or the Cloud API. What does a "403 on checkpoints" ticket usually turn out to be: wrong endpoint, wrong location, or the wrong kind of key?
- Public docs list several S3 features that are not currently supported, including server-side encryption and lifecycle policies. When a customer assumes AWS S3 behavior, how do you want that gap communicated so it does not become a P1 about "lost" objects?

## Cross-product, docs, and the escalation practice itself

- Customers can sign up for a Managed AI account or an Infrastructure Cloud account, and the docs say they can switch in the console. When a ticket spans inference and VMs, who is the owner of record, and how is the handoff written down?
- The create-an-account page says you must add a payment method to use the managed inference service. The 19 August 2026 updates page says introductory credits can be used for Serverless Inference and Serverless Fine-Tuning without a payment method. See https://docs.crusoe.ai/create-an-account.md and https://docs.crusoe.ai/updates/2026/august/. Which page is the source of truth for a new user, and how do docs mismatches get fixed?
- What is the current customer-update cadence for P0 and P1, and who notices when an update is missed?
- When should a repeating P2 become a product or docs change rather than another well-written ticket? Who accepts that feedback, and how does an escalation manager see it close?
- What metric would you actually look at in 90 days to decide whether escalations are getting better: time to mitigation, missed comms, recurrence, or something else?
- For a silent failure like HTTP 200 with empty `content`, where should the detection live — customer monitors, Crusoe-side checks, or both — and what would you want to have in place before the next model launch?
