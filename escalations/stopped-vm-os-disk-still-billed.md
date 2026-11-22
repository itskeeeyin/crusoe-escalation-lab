# Example escalation: unexpected storage charges after VMs are stopped

This is an example customer escalation built from **public Crusoe billing and shared-disk FAQs**. It is **documented, not reproduced**. This lab did not create, stop, or resize any VM or disk. The customer name and any dollar impact below are **hypothetical**.

Suggested severity: **P2**, customer updates **daily**. This is unexpected ongoing spend, not an outage. Workloads may already be stopped. Promote to **P1** (updates every 4 hours) if the unexpected charge is material for that customer, or if they cannot delete or resize the disks that are still billing.

A hypothetical illustrative impact, not a real invoice: a stopped VM whose 128 GiB OS persistent disk is left behind would accrue about 128 × $0.08 = **$10.24 per month** at the October 2025 public persistent-disk list price, plus any detached data disks, until those disks are deleted. Shared disks are billed on provisioned capacity at $0.07/GiB/month even when detached. Those figures are from public pricing pages, applied to a hypothetical leftover disk, not from this account's bill.

## Source (real public report)

Crusoe Support, "FAQ: On-Demand Billing Questions," updated 24 December 2025:

https://support.crusoecloud.com/hc/en-us/articles/31619771210267-FAQ-On-Demand-Billing-Questions

Question 3, "Are my VMs being charged when they're stopped?": "Stopped VMs are not charged for on-demand usage, but you will still be billed for the 128GB OS Persistent disk until the VM is deleted."

Question 4, "How are my disks charged?": "Ephemeral disks are included in the VM pricing and will not incur additional costs. Persistent (including OS disks) and Shared disks are billed regardless of whether or not they are attached to a running VM. Persistent (including OS disks) and Shared disks will stop being billed once these disks are deleted." The same answer warns: "Make sure you migrate any data off of the persistent and shared disk before deleting."

Supporting public pricing and resize guidance:

- "FAQ: Determining On-Demand Pricing for Crusoe Offerings," updated 20 October 2025, lists Block Storage (Persistent Disk) at $0.08 per GiB/month and Shared Disk at $0.07 per GiB/month as of October 2025: https://support.crusoecloud.com/hc/en-us/articles/37421109850907-FAQ-Determining-On-Demand-Pricing-for-Crusoe-Offerings
- "FAQ: Crusoe Shared Disk Resizing" states "The billing is done based on the provisioned size. That's why it is wiser to provision only a disk size that you will use," and `crusoe storage disks resize <name> --size <size>` can downsize a shared disk, but not below current usage: https://support.crusoecloud.com/hc/en-us/articles/44584497994139-FAQ-Crusoe-Shared-Disk-Resizing

## Customer symptom

Hypothetical customer: a team stops GPU or CPU VMs at the end of a job, or after a training run, expecting the bill to go to zero. The next invoice still shows persistent-disk or shared-disk charges. They open a ticket: "we stopped the VMs, why are we still being billed?" or "our storage line item does not match the data we think we are using."

## Reproduction status

**Documented, not reproduced.** No VM or disk was provisioned, stopped, detached, or deleted on this account. Evidence below is the public FAQs only.

## Hypotheses and tests

| ID | Hypothesis | Test | Result |
| --- | --- | --- | --- |
| H1 | The VMs themselves are still in a running state, including lifecycle scripts | `crusoe compute vms list` (or the Console) and confirm state is stopped, not running | Not run here. The billing FAQ says running-state time, including lifecycle scripts, is what incurs VM charges. |
| H2 | The 128 GB OS persistent disk still exists because the VM was stopped, not deleted | List disks attached to the stopped VM | Not run here. The FAQ states that disk is billed until the VM is deleted. |
| H3 | Detached persistent or shared data disks were left behind after the VM was deleted | `crusoe storage disks list` and compare to the invoice line items | Not run here. The FAQ states those disks bill until deleted, attached or not. |
| H4 | A shared disk is billed on provisioned TiB, not on used bytes, so "we only stored 3 TB" does not match a 20 TiB volume | Confirm provisioned size versus used capacity; consider a resize that stays above used capacity | Not run here. The resize FAQ is explicit that billing follows provisioned size. |
| H5 | A pricing or invoice bug, rather than leftover disks | Match each invoice SKU to a still-existing disk or stopped VM | Not run here. Do not tell the customer it is a billing bug until leftover disks are ruled out. |

## Workaround

- Stopping a VM stops VM compute charges. It does not stop OS-disk charges. Delete the VM if the disk is no longer needed, after migrating any data you must keep.
- List persistent and shared disks in the project, including disks that are not attached to a running VM, and delete only those whose data has been migrated.
- For an oversized shared disk, resize down to just above used capacity rather than leaving a large provisioned volume idle. Per the resize FAQ, custom QoS is cleared by a resize; contact Crusoe support before resizing a disk that has custom QoS, because default settings can cause "extreme write latency."
- Set a recurring inventory check: stopped VMs, detached persistent disks, and provisioned shared-disk size versus actual use.

## Long-term fix and engineering ask

Practice recommendations, not a claim about Crusoe's roadmap:

- In the Console stop-VM confirmation, state clearly that the OS persistent disk will keep billing until the VM is deleted.
- Show an "idle but still billing" view of detached persistent and shared disks, with estimated monthly cost at the public list price.
- On the invoice, group leftover-disk charges next to the VM that used to own them, so the first ticket is not "mystery storage spend."

## Customer updates (P2, daily)

Hypothetical comms. No real customer received these.

**Day 1:**

> We're reviewing the unexpected storage charges after the VMs were stopped. On Crusoe, stopped VMs are not charged for on-demand compute, but the 128 GB OS persistent disk is still billed until the VM is deleted, and persistent or shared data disks are billed whether or not they are attached. Please send the invoice line items, project ID, and a list of VMs and disks in the project. Next update tomorrow, or sooner once we can match those line items to leftover disks.

**Day 2:**

> Public billing docs match this shape: leftover OS and data disks continue to bill until they are deleted, and shared disks are billed on provisioned size, not used bytes. Workaround: migrate any data you need to keep, then delete the disks (or the stopped VMs) you no longer need; if a shared disk is only oversized, resize it down but not below current usage. Next update tomorrow, or sooner after you confirm the leftover inventory.

**Day 3 (mitigated):**

> The remaining charges are consistent with disks that still exist after compute was stopped, not with a compute-billing leak. Please keep the disk inventory check in place. We're closing this P2. If charges continue after the leftover disks are gone, or if a disk cannot be deleted, we will reopen and escalate.

## Lessons

- "We stopped the VMs" is not "storage billing stopped." Ask for a disk inventory on the first call.
- Shared-disk surprises are often provisioned size versus used bytes, not a unit-price error.
- Never recommend a delete before the customer has migrated data, and never recommend a shared-disk resize when custom QoS is in place without looping in support.

No lab spend. This issue was not reproduced.
