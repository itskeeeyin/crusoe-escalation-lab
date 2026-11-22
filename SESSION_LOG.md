# Paid-session log

Attempts to execute [`PAID_SESSION_PLAN.md`](PAID_SESSION_PLAN.md). Customer names and dollar figures in the related write-ups stay hypothetical. Credentials were never printed or committed. Local CLI config, if any, was deleted at the end of each sitting.

## Sitting 2 — 21 November 2026, 7:25 PM PT (America/Los_Angeles)

Clock restart: **7:25:00 PM PT**. Hard time box 90 minutes, teardown by **8:35 PM PT**, spend cap $3, CPU-only, names prefixed `lab-esc-`. New Cloud API keys were in the environment (`CRUSOE_ACCESS_KEY_ID` was confirmed different from `CRUSOE_API_KEY`; values not printed).

**Result: authentication succeeded. Both create attempts were rejected for quota and were skipped (a quota increase or support ticket would have been required). No paid resources were created. Estimated cost: $0.00.**

None of the three infrastructure issues was reproduced.

### Timeline

| Time PT | Event |
| --- | --- |
| 7:25:00 PM | Clock start. Crusoe CLI v1.1.0 already installed. |
| 7:25:09 PM | `crusoe whoami` succeeded: Cian O Mahony (email redacted). Project `verdant-seed-105` is the only project (role org-admin). Locations: `us-east1-a`, `eu-iceland1-a`, `us-southcentral1-a`. |
| 7:25:28 PM | Starting inventory succeeded. **No VMs, no disks, no Kubernetes clusters, no load balancers.** Default VPC, three default subnets, and default firewall rules already existed and were not created by this sitting. Smallest CPU type is `c1a.2x` (2 vCPU, 8 GiB). |
| 7:25:55 PM | Generated a throwaway SSH key for the sitting (not committed). |
| 7:26:04 PM | `crusoe storage disks create --name lab-esc-data --size 1GiB --location us-southcentral1-a` failed: `Error: could not create Disk: You have reached your quota for Persistent SSD Disks. Please contact support to increase your quota for Persistent SSD Disks`. |
| 7:26:04 PM | `crusoe compute vms create --name lab-esc-cpu --type c1a.2x --location us-southcentral1-a --image ubuntu22.04:latest` failed: `Error: could not create VM: You have reached your quota for General-Purpose CPU (C1A). Please contact support to increase your quota for General-Purpose CPU (C1A)`. |
| 7:26:04 PM | Both steps skipped. No support ticket and no quota-increase request were opened, per the plan. |
| 7:26:31 PM | Post-error inventory: still no VMs, disks, clusters, or load balancers. |
| 7:26:48 PM | Full teardown verification list commands (below). No `lab-esc-` resources. |
| 7:26:59 PM | Deleted the throwaway SSH key. No local `~/.crusoe` or `/workspace/.crusoe-lab` config was present (auth used env vars only). Session stopped. |

CMK cluster and load-balancer steps were not started. A CPU node pool would have used the same C1A and Persistent SSD quotas that already rejected the VM and data disk.

s1a instance types were not used. The smallest s1a is `s1a.20x` (20 vCPU), which is not the planned smallest size and was not needed once the planned C1A path required a quota ticket.

### Starting inventory (7:25:28 PM PT, redacted)

```
VMs:        no vm found
Disks:      no disk found
Clusters:   (empty)
LBs:        (empty)
Subnets:    default-subnet-us-east1-a, default-subnet-us-southcentral1-a, default-subnet-eu-iceland1-a
            (pre-existing; IDs redacted; not named lab-esc-)
Firewall:   default-allow-ssh, default-allow-*-egress, default-allow-subnet-* in each default subnet
            (pre-existing; IDs redacted; not named lab-esc-)
```

### Create errors (verbatim)

```
Error: could not create Disk: You have reached your quota for Persistent SSD Disks. Please contact support to increase your quota for Persistent SSD Disks

Error: could not create VM: You have reached your quota for General-Purpose CPU (C1A). Please contact support to increase your quota for General-Purpose CPU (C1A)
```

### Teardown verification — 7:26:48 PM PT

**Mandatory teardown result: no `lab-esc-` VM, disk, node pool, cluster, load balancer, firewall rule, VPC, or subnet was created in this sitting, so there was nothing to delete.**

Unlike sitting 1, inventory list commands **succeeded**. Output:

```
===== VMS =====
no vm found

===== DISKS =====
no disk found

===== CLUSTERS =====
(empty table — no clusters, therefore no node pools)

===== LOAD BALANCERS =====
(empty table)

===== FIREWALL RULES =====
default-allow-ssh
default-allow-icmp-egress
default-allow-tcp-udp-egress
default-allow-subnet-icmp-us-east1-a
default-allow-subnet-tcp-udp-us-east1-a
default-allow-subnet-icmp-us-southcentral1-a
default-allow-subnet-tcp-udp-us-southcentral1-a
default-allow-subnet-icmp-eu-iceland1-a
default-allow-subnet-tcp-udp-eu-iceland1-a
(all pre-existing default rules; none named lab-esc-)

===== SUBNETS =====
default-subnet-us-east1-a
default-subnet-us-southcentral1-a
default-subnet-eu-iceland1-a
(all pre-existing default subnets; none named lab-esc-; none created in this sitting)
```

A search of the list outputs for the string `lab-esc-` found matches only in the local headings of the failed create command logs, not in any API list of resources.

Pre-existing default VPC, subnets, and default firewall rules were left in place. They were not created by this sitting and were not deleted.

### Cost

Estimated cost of sitting 2: **$0.00**. Hard cap was $3. No compute, disk, cluster, or load balancer was provisioned.

### Follow-up

The three infrastructure reproductions need a non-zero quota for General-Purpose CPU (C1A) and Persistent SSD Disks (including the 128 GiB OS disk that comes with a VM). That requires a quota increase in the console or a support ticket, which this sitting was instructed to skip.

## Sitting 1 — 21 November 2026, 7:18 PM PT (America/Los_Angeles)

Clock start: **7:18:45 PM PT**. Stopped at authentication. `crusoe whoami` returned `Error: could not get identity: failed to authenticate user` (feature-flag fetch HTTP 401). The Cloud CLI access key in the environment was the same string as the Intelligence API key, a different credential type. No create commands were issued. Estimated cost: **$0.00**. Inventory list commands could not be run in that sitting. Details are kept here for the record; sitting 2 supersedes the auth problem.
