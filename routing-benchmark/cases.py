"""SYNTHETIC triage cases for the routing benchmark.

Every ticket below is invented. They are modeled on public Crusoe support and
docs topics (VM boot failures, quota, billing for stopped VMs, CMK autoscaler,
load balancer health checks, fine-tune validation, Serverless Inference 429s
and empty completions). Customers, numbers and symptoms are fictional.

Labels follow the rubric in the prompt (see bench.py):
  priority   P1-P4   (impact x urgency)
  area       one of AREAS
  team       one of TEAMS
difficulty: "easy" = one clear signal; "hard" = misleading cue, anomaly vs.
documented behavior, or priority that is easy to inflate/deflate.
"""

AREAS = ["gpu_vm", "networking", "storage", "kubernetes", "inference",
         "fine_tuning", "billing_quota"]
TEAMS = ["compute_oncall", "network_eng", "storage_eng", "cmk_eng",
         "inference_eng", "ml_platform_eng", "billing_quota_ops",
         "security_oncall", "support_tier1"]

CASES = [
    # ---- easy ----
    ("easy", "Our production inference API runs on a single 8xH100 VM. It crashed an hour ago and will not boot after reboot: the console is blank and the state stays 'Starting'. Our customer-facing product is completely down and we have no spare capacity.",
     "P1", "gpu_vm", "compute_oncall"),
    ("easy", "Launching 2 more H100 VMs for our staging cluster fails with 'quota exceeded for h100-80gb-sxm-ib.8x'. No deadline, we just want the limit raised when you can.",
     "P3", "billing_quota", "billing_quota_ops"),
    ("easy", "I stopped my VM last week but I am still seeing charges on it. Why am I being billed for a stopped instance? It is a personal dev box, nothing is broken.",
     "P4", "billing_quota", "support_tier1"),
    ("easy", "Our nightly offline batch job calls Serverless Inference and gets HTTP 429 after about 700 requests per minute. We have no payment method on the account yet. Job is non-production and retries eventually finish.",
     "P3", "inference", "support_tier1"),
    ("easy", "CMK node pool autoscaler is not scaling up: 14 pods have been Pending for 2 hours and the pool sits at its minimum size. Our production web tier is a bit slow, but we manually added 3 nodes and it is coping. We would like the autoscaler fixed this week.",
     "P3", "kubernetes", "cmk_eng"),
    ("easy", "Right now a brand new load balancer shows every backend as unhealthy and all production traffic to our app has been failing for 10 minutes. Backends respond 200 on the health path when we curl them directly from inside the VPC.",
     "P1", "networking", "network_eng"),
    ("easy", "Our fine-tuning job failed at validation with: 'dataset schema invalid: missing messages field at line 4211'. This is a test run, no deadline. Is our JSONL wrong?",
     "P3", "fine_tuning", "support_tier1"),
    # ---- hard ----
    ("hard", "Foundry returns HTTP 200 with an empty content string for roughly 1 in 5 requests to a reasoning model. We set max_tokens to 256. The finish_reason is 'length' and usage shows ~250 completion tokens. Dev environment only, we are evaluating.",
     "P3", "inference", "support_tier1"),
    ("hard", "Our 64-GPU training job's NCCL all-reduce bandwidth dropped about 40% since yesterday. dmesg on nodes in the same rack shows InfiniBand link down/up flaps. The job is still running but at reduced speed, and we have a model release deadline in 20 hours that we will miss at this speed.",
     "P2", "networking", "network_eng"),
    ("hard", "We resized a persistent disk from 2TB to 4TB and the VM now drops into emergency mode because /data will not mount. dmesg shows repeated I/O errors on the device. Our production database lives on it and has been offline for 25 minutes. Snapshots from last night exist.",
     "P1", "storage", "storage_eng"),
    ("hard", "Intermittent 429s from Serverless Inference: only about 5 requests per minute, and the x-ratelimit-remaining-tokens header shows nearly 2,000,000 remaining, with a payment method on file. Only one model is affected. About 30% of our production chatbot users see errors.",
     "P2", "inference", "inference_eng"),
    ("hard", "We stopped all our VMs three weeks ago, yet this month's invoice shows $11,800 of H100 compute hours, around 40 hours per day. Payment is due in about 48 hours. Nothing is broken operationally but the amount is not plausible.",
     "P3", "billing_quota", "billing_quota_ops"),
    ("hard", "A CMK upgrade from 1.31 to 1.32 has been stuck at 60% for 5 hours and the API server times out intermittently. Running workloads are fine, but we cannot deploy, and a release is scheduled for tomorrow morning with no way around the upgrade.",
     "P2", "kubernetes", "cmk_eng"),
    ("hard", "One of our Intelligence Foundry API keys was pushed to a public GitHub repo. Usage is now about 3M tokens per hour from IP addresses we do not recognize and the spend keeps climbing. We have not revoked it yet.",
     "P1", "inference", "security_oncall"),
    ("hard", "GPU 3 on one of our 8-GPU VMs logged 'Xid 79: GPU has fallen off the bus' for the third time this week. Our training framework restarts from checkpoint automatically, losing about 10 minutes each time. We would like the node replaced when convenient.",
     "P3", "gpu_vm", "compute_oncall"),
    ("hard", "Launching a VM returns 'quota exceeded' but the console shows 0 of 16 H100 GPUs in use in that region. We have a customer demo in 3 hours that needs this capacity.",
     "P2", "billing_quota", "billing_quota_ops"),
    ("hard", "A fine-tuning job on a 200 MB JSONL has been in 'Validating' for 14 hours. Other jobs from our team validated in about 10 minutes yesterday. Non-production experiment, no deadline.",
     "P3", "fine_tuning", "ml_platform_eng"),
]
