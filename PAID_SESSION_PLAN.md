# Paid-session plan: three infrastructure escalations

This is a **plan only**. It is for a single sitting, on this account, to reproduce three issues that were documented from public Crusoe articles and **not** reproduced in the cheap Serverless lab:

1. Stopped VMs still billed for leftover persistent disks.
2. CMK Cluster Autoscaler unhealthy-pool deadlock.
3. CMK load balancer shows backends `Online` while client requests time out (missing NodePort firewall rule).

**Do not run this plan as part of an unattended lab. Do not create any paid resources until a later, explicit go-ahead.** This file does not authorize `terraform apply`, `crusoe compute vms create`, cluster create, or load-balancer create.

Customer names and dollar impact in the related write-ups stay hypothetical. Public list prices below are not an invoice.

## Goal and hard time box

Wall-clock budget: **90 minutes**. Start teardown no later than **T+70 minutes**, whether or not all three issues reproduced. If anything is still creating nodes, load balancers, or disks at T+70, tear it down first and stop.

Order of work:

1. Disk billing on a stopped CPU VM (about 20 minutes).
2. CMK autoscaler deadlock on a **CPU-only** pool (about 30 minutes).
3. Load-balancer Online-but-timeout on that same cluster (about 20 minutes).
4. Teardown and verification (at least 20 minutes, earlier if the clock runs out).

Do not use GPU instance types in this sitting. Do not set an autoscaler max of 254. Do not leave an unfulfillable desired count in place when you walk away.

## Public prices used for the estimate

| Item | Public figure | Source |
| --- | --- | --- |
| CPU VMs | $0.04 per vCPU-hour | Provided for this plan; confirm on https://www.crusoe.ai/cloud/pricing before you start |
| Persistent (block) disk | $0.08 per GiB-month, billed while the disk exists, attached or not | https://support.crusoecloud.com/hc/en-us/articles/37421109850907-FAQ-Determining-On-Demand-Pricing-for-Crusoe-Offerings (as of October 2025) and https://support.crusoecloud.com/hc/en-us/articles/31619771210267-FAQ-On-Demand-Billing-Questions |
| Crusoe Managed Kubernetes | $0.10 per cluster-hour | Same on-demand pricing FAQ, October 2025 |
| Load balancer | **Unknown** from public docs used here | No list price was found in the load-balancer guide. Treat LB cost as an unquoted line item: create it only if you are willing to pay an unknown rate for a few minutes, and delete it in the same sitting |

Supporting VM size, from https://docs.crusoe.ai/compute/virtual-machines/overview.md: `c1a.2x` is a 2 vCPU, 8 GB AMD Genoa instance, and is the smallest documented `c1a` size. At $0.04/vCPU-hour that is **$0.08 per hour** while the VM is running. Stopped on-demand VMs are not charged for compute, but the default **128 GiB OS persistent disk** remains until the VM is deleted: 128 × $0.08 = **$10.24 per month**, or about **$0.014 per hour**, if it is left behind.

### Estimated spend if the sitting stays inside the box

Assumes one `c1a.2x` VM (possibly also used as a CMK node type if that type is offered; if CMK has a different smallest CPU type, recompute before apply), one CMK cluster, at most **two** CPU nodes, no GPUs, and teardown at or before 90 minutes.

| Resource | Formula | Estimate for 90 minutes |
| --- | --- | --- |
| One `c1a.2x` running 20 minutes (disk-billing step) | 2 × $0.04 × 20/60 | ~$0.027 |
| 128 GiB OS disk for that VM, 90 minutes | $10.24 / 730 hours × 1.5 | ~$0.021 |
| Optional 1 GiB data disk, 90 minutes | $0.08 / 730 × 1.5 | ~$0.0002 |
| One CMK cluster, 70 minutes | $0.10 × 70/60 | ~$0.117 |
| One or two CPU worker nodes, ~60 minutes (if `c1a.2x`) | $0.08 or $0.16 | ~$0.08–$0.16 |
| Worker OS disks, 60–90 minutes | ~$0.014 each | ~$0.014–$0.042 |
| Load balancer | unknown | reserve an unknown amount; delete immediately after evidence |
| **Subtotal excluding LB** |  | **about $0.26–$0.37** |
| If teardown is missed and one 128 GiB OS disk is left for a month | 128 × $0.08 | **$10.24** |

If regional CPU types for CMK are larger than `c1a.2x`, stop and re-estimate. If a scale-up starts more than two nodes, lower `--count` immediately.

## Shared setup (read-only until go-ahead)

```bash
# Confirm CLI auth and the project you think you are in
crusoe projects list
crusoe locations list
crusoe compute vms types
crusoe kubernetes versions list

# Starting inventory — save this output. Teardown is not done until these are empty
# of the resources you created (names prefixed lab-esc-).
crusoe compute vms list
crusoe storage disks list
crusoe kubernetes clusters list
crusoe networking load-balancers list
crusoe networking vpc-firewall-rules list
crusoe networking vpc-subnets list
```

Prefix every created name with `lab-esc-` so teardown can be grepped. Prefer the default VPC only if you understand its default firewall rules; a custom VPC starts with implicit deny (https://docs.crusoe.ai/networking/firewall-rules/overview/).

## 1. Stopped VM, leftover disk billing

Public issue: https://support.crusoecloud.com/hc/en-us/articles/31619771210267-FAQ-On-Demand-Billing-Questions

CLI, from https://docs.crusoe.ai/quickstart/creating-a-vm/, https://docs.crusoe.ai/compute/virtual-machines/managing-vms.md, and https://docs.crusoe.ai/storage/disks/managing-persistent-disks.md:

```bash
# Smallest documented CPU VM. Confirm type and location first.
crusoe compute vms create \
  --name lab-esc-cpu \
  --type c1a.2x \
  --location us-southcentral1-a \
  --image ubuntu22.04:latest \
  --keyfile ~/.ssh/id_ed25519.pub

# Optional 1 GiB data disk, to show a detached disk still exists after stop/delete of the VM
# (only if you will delete it in this sitting).
crusoe storage disks create \
  --name lab-esc-data \
  --size 1GiB \
  --location us-southcentral1-a
crusoe compute vms attach-disks lab-esc-cpu --disk name=lab-esc-data,mode=read-write

# Capture running inventory
crusoe compute vms list
crusoe storage disks list

# Stop the VM. Compute should stop billing; disks should still be listed.
crusoe compute vms stop lab-esc-cpu
crusoe compute vms list
crusoe storage disks list
```

Terraform equivalent (plan only until go-ahead), from the same disk and VM docs:

```hcl
resource "crusoe_storage_disk" "lab_esc_data" {
  name     = "lab-esc-data"
  size     = "1GiB"
  location = "us-southcentral1-a"
}

resource "crusoe_compute_instance" "lab_esc_cpu" {
  name     = "lab-esc-cpu"
  type     = "c1a.2x"
  location = "us-southcentral1-a"
  image    = "ubuntu22.04:latest"
  ssh_key  = file("~/.ssh/id_ed25519.pub")
  disks = [{
    id              = crusoe_storage_disk.lab_esc_data.id
    mode            = "read-write"
    attachment_type = "data"
  }]
}
```

Evidence to capture:

- Timestamped `vms list` while running and after `stop` (instance state `stopped`).
- Timestamped `disks list` showing the 128 GiB OS disk still present after stop, and the 1 GiB data disk still present if you created it.
- After later VM delete: whether the OS disk is gone, and whether a previously attached data disk remains (the billing FAQ says persistent disks bill until **deleted**, not until detached).
- Do not expect a new invoice to land in 20 minutes. The evidence is leftover disks that the public price list would still charge.

## 2. CMK autoscaler unhealthy-pool deadlock

Public issue: https://support.crusoecloud.com/hc/en-us/articles/50644854495387-CMK-Cluster-Autoscaler-Best-practices-and-Known-Limitations

CLI, from https://docs.crusoe.ai/orchestration/cmk/managing-clusters.md and https://docs.crusoe.ai/orchestration/cmk/managing-nodepools.md:

```bash
# Use a current minor from `crusoe kubernetes versions list` and a real subnet id.
# Keep add-ons minimal if you can; the examples include GPU operators, which this sitting does not need.
crusoe kubernetes clusters create \
  --name lab-esc-cmk \
  --cluster-version 1.35 \
  --location us-east1-a \
  --subnet-id <subnet-id>

# Smallest CPU node type available in that location — confirm before running.
# Start at count=1. Do not start at a GPU type or a large count.
crusoe kubernetes nodepools create \
  --name lab-esc-cpu-pool \
  --cluster-name lab-esc-cmk \
  --type <smallest-cpu-type> \
  --count 1 \
  --keyfile ~/.ssh/id_ed25519.pub

crusoe kubernetes nodepools list --cluster-name lab-esc-cmk
```

Install or confirm the Cluster Autoscaler add-on only if the cluster supports it. List **every** pool in `--nodes`, with a tight max (example `1:2`, never an implicit `1:254`).

To approach the deadlock **safely**: raise desired count by **one** above what you already know can be provisioned (for example, quota or observed capacity is 1, set `--count 2`). Do not jump to a large number. Watch:

```bash
crusoe kubernetes nodepools list --cluster-name lab-esc-cmk
# Look for STATE_UNHEALTHY, desired count above running count, and health issues.
```

If the pool goes unhealthy, capture autoscaler logs (`kubectl -n crusoe-system logs` on the autoscaler pod) for the documented abort line, then **reset the cloud-side count immediately**:

```bash
crusoe kubernetes nodepools update lab-esc-cpu-pool --count <actual-running-count>
```

Wait until the pool is `STATE_RUNNING` (the article says up to a minute) before doing anything else.

Terraform sketch (plan only), from the cluster and node-pool docs. Replace version, subnet, and type after the list commands:

```hcl
resource "crusoe_kubernetes_cluster" "lab_esc" {
  name      = "lab-esc-cmk"
  version   = "1.35"
  location  = "us-east1-a"
  subnet_id = "<subnet-id>"
}

resource "crusoe_kubernetes_node_pool" "lab_esc_cpu" {
  name           = "lab-esc-cpu-pool"
  cluster_id     = crusoe_kubernetes_cluster.lab_esc.id
  type           = "<smallest-cpu-type>"
  instance_count = 1
  ssh_key        = file("~/.ssh/id_ed25519.pub")
}
```

Evidence to capture:

- `nodepools list` / `get` showing desired versus running count and `STATE_UNHEALTHY`.
- The abort log line from the public article, if it appears.
- The update command and the return to `STATE_RUNNING`.
- If the pool never goes unhealthy (capacity was available), **do not keep raising count**. Record "not reproduced, capacity was available" and move on.

## 3. Load balancer Online, clients time out

Public issue: https://support.crusoecloud.com/hc/en-us/articles/54052858599963-How-To-Manage-Load-Balancer-Firewall-Rules-Automatically-on-CMK

Reuse the cluster from step 2. Do not create a second cluster. Load-balancer **price is unknown**; if you skip this step because of that, say so in the notes and still tear down everything from steps 1 and 2.

```bash
# A tiny Service without the firewall annotation, on a NodePort the cluster already has
# (deploy a one-replica CPU hello app first). Then:
kubectl get svc lab-esc-svc
crusoe networking load-balancers list
crusoe networking vpc-firewall-rules list
```

Evidence to capture:

- Service has an external IP; load-balancer backends show `Online`.
- `vpc-firewall-rules list` has **no** ingress rule for that Service's NodePort.
- `nc -zv <EXTERNAL_IP> <PORT>` from your client times out or is refused.
- After `kubectl annotate svc lab-esc-svc crusoe.ai/manage-firewall-rule=true` and a tight `loadBalancerSourceRanges` (your IP only, never `0.0.0.0/0` unless you intend a public NodePort), a rule appears and the same `nc` succeeds.
- Controller logs as in the article, if useful.

A standalone CLI LB (https://docs.crusoe.ai/networking/load-balancers/managing-load-balancers.md) is optional and also unpriced here:

```bash
# Only if you are not using a Service and still want a CLI LB — same unknown price.
crusoe networking load-balancers create \
  --name lab-esc-lb \
  --location us-east1-a \
  --vpc-network-id <vpc-id> \
  --protocol tcp \
  --listener 80,<backend-ip>:80
```

Prefer the Kubernetes Service path; it is the one the support article describes.

## Teardown checklist (start by T+70)

Do this in order. Migrate no data — these are lab resources.

```bash
# 1. Kubernetes Services and controller-managed firewall rules
kubectl delete svc lab-esc-svc --ignore-not-found
# If you set the annotation to "false", the rule may be left behind. Delete it by id.
crusoe networking vpc-firewall-rules list
# crusoe networking vpc-firewall-rules delete <RULE_ID>

# 2. Load balancers
crusoe networking load-balancers list
# crusoe networking load-balancers delete <name-or-id>

# 3. Node pools first, then the cluster
# https://docs.crusoe.ai/orchestration/cmk/managing-nodepools.md
# https://docs.crusoe.ai/orchestration/cmk/managing-clusters.md
crusoe kubernetes nodepools list --cluster-name lab-esc-cmk
# If desired count is still above running count, reset it first.
# crusoe kubernetes nodepools update lab-esc-cpu-pool --count <actual-running-count>
crusoe kubernetes nodepools delete lab-esc-cpu-pool
crusoe kubernetes clusters delete lab-esc-cmk

# 4. The standalone CPU VM and disks
# Detach before disk delete if needed:
# crusoe compute vms detach-disks lab-esc-cpu --disk name=lab-esc-data
crusoe compute vms stop lab-esc-cpu || true
crusoe compute vms delete lab-esc-cpu
crusoe storage disks delete lab-esc-data
# Deleting the VM should remove its OS disk; still list disks and delete leftovers.

# 5. If this sitting used Terraform, destroy after the CLI check, or instead of the CLI deletes:
# terraform destroy
```

### Verification — do not leave the sitting until these are empty of `lab-esc-` resources

```bash
crusoe compute vms list
crusoe storage disks list
crusoe kubernetes clusters list
# If any cluster remains:
#   crusoe kubernetes nodepools list --cluster-name <name>
crusoe networking load-balancers list
crusoe networking vpc-firewall-rules list
```

Confirm:

- No `lab-esc-` VMs in any state, including `stopped`.
- No leftover 128 GiB OS disks or `lab-esc-data` disks. This is the line item that keeps billing at $0.08/GiB-month.
- No `lab-esc-cmk` cluster and no leftover node pools.
- No `lab-esc` load balancers.
- No firewall rule created for this sitting that is still open (especially not `0.0.0.0/0` on a NodePort).

Save the verification output next to the evidence. If anything remains, it is not torn down.

## What this sitting is not

- It is not a GPU or Slurm test.
- It is not a reservation or committed-instance test (stopped committed VMs can still incur compute charges; stay on-demand).
- It is not authorization to spend beyond the estimates above, or to leave disks overnight.
