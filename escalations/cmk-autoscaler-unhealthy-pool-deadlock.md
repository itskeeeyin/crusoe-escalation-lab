# Example escalation: CMK Cluster Autoscaler stuck after a pool goes `STATE_UNHEALTHY`

This is an example customer escalation built from a **public Crusoe Support known-limitations article**. It is **documented, not reproduced**. This lab did not create a Crusoe Managed Kubernetes cluster or scale a node pool. The customer name and any dollar impact below are **hypothetical**.

Suggested severity: **P1**, customer updates **every 4 hours**. Pending pods cannot scale onto the unhealthy pool, and if the expander keeps selecting that pool, they can stay pending even when another healthy pool exists. Existing nodes can still serve traffic, so this is not automatically a P0. Use P0 (hourly updates) only if user-facing capacity is already exhausted and there is no healthy alternate pool.

## Source (real public report)

Crusoe Support, "CMK Cluster Autoscaler: Best practices and Known Limitations," updated 27 May 2026:

https://support.crusoecloud.com/hc/en-us/articles/50644854495387-CMK-Cluster-Autoscaler-Best-practices-and-Known-Limitations

The article is validated against `crusoe-cluster-autoscaler-release-1.30.3` in the `crusoecloud/k8s-autoscaler` repository. Limitation 1, "Unhealthy Node Pool Deadlock," states: "When a node pool's desired count exceeds what Crusoe Cloud can provision, the pool transitions to `STATE_UNHEALTHY`. The autoscaler then forces its internal target size to the number of currently active nodes, but the cloud-side desired count is still the higher (unfulfillable) number." After that, "every `IncreaseSize` call is silently aborted."

The logged line, every ~10 seconds, is:

```
IncreaseSize,PoolID=<pool-id>, aborting IncreaseSize. Current node pool count on Crusoe Cloud already exceeds node group's target size
```

The article also warns that the autoscaler is not reservation-aware: a pool configured as `--nodes=1:10:my-pool` against a 5-VM reservation will request 10 VMs, bill the extra 5 on-demand, and "if on-demand inventory is also constrained, the pool can transition to `STATE_UNHEALTHY` and block further scale-up entirely." A second foot-gun: a pool omitted from `--nodes` is not ignored; it inherits `min=1, max=254`.

Recovery, from the same article, is to reset the cloud-side desired count to the number of VMs that are actually running:

```
crusoe kubernetes nodepools update <pool-name-or-id> --count <actual-running-count>
```

then wait for `STATE_RUNNING` (up to a minute).

## Customer symptom

Hypothetical customer: a burst of pending pods should have added GPU or CPU nodes. The pods stay pending. Autoscaler logs repeat an `IncreaseSize` abort every ten seconds. `crusoe kubernetes nodepools list` shows the pool in `STATE_UNHEALTHY`. They open a P1: "autoscaler is broken" or "CMK will not scale up."

## Reproduction status

**Documented, not reproduced.** No CMK cluster or node pool was created on this account. Evidence below is the public article only.

## Hypotheses and tests

| ID | Hypothesis | Test | Result |
| --- | --- | --- | --- |
| H1 | The cluster or autoscaler pod is down | `kubectl -n crusoe-system get deploy,pods` and check API access | Not run here. The article notes the autoscaler can keep working even if its host node is `NotReady`, as long as it can reach both APIs. |
| H2 | The pool is in `STATE_UNHEALTHY` because desired count exceeded what could be provisioned (quota or capacity) | `crusoe kubernetes nodepools list`; compare desired count to running instances; look for the abort log line every ~10 seconds | Not run here. This is the documented deadlock. |
| H3 | The expander is "shadowing" a healthy alternate pool by repeatedly picking the unhealthy one | Check pending pods, expander decisions, and whether another pool could fit them | Not run here. The article describes this interaction explicitly. |
| H4 | A pool was omitted from `--nodes` and inherited `1:254`, then tried to grow past available capacity | Diff the autoscaler Deployment args against every pool name | Not run here. The article warns that an unlisted pool is not ignored. |
| H5 | The scale-up is hitting the 30-minute operation timeout rather than the deadlock | Autoscaler logs for timeout errors; regional capacity or quota | Not run here. Limitation 6 in the same article covers that path. |

## Workaround

- Confirm the pool is `STATE_UNHEALTHY` and that the abort log line is present.
- Reset the cloud-side desired count to the actual running count: `crusoe kubernetes nodepools update <pool-name-or-id> --count <actual-running-count>`. Wait for `STATE_RUNNING`.
- If the unhealthy pool has idle nodes, scale-down can self-heal by lowering the cloud-side count. The article says that only helps when utilization is dropping; for a growing workload, run the CLI reset.
- List every pool in `--nodes`. Freeze fixed-size pools with `min == max`. Prefer the article's reserved-plus-on-demand two-pool pattern so a reservation is not overrun into an unhealthy state.
- Set `--skip-nodes-with-local-storage=false` so system `emptyDir` volumes do not also block scale-down (a separate, documented foot-gun).

## Long-term fix and engineering ask

Practice recommendations, not a claim about Crusoe's roadmap:

- When `IncreaseSize` is aborted because cloud-side count exceeds target, emit a clear condition or event on the node pool, not only a log line every 10 seconds.
- Make the autoscaler reservation-aware, or refuse to raise desired count past reserved size unless an on-demand burst pool is explicitly configured.
- Treat a pool omitted from `--nodes` as frozen at its current size, or fail startup, rather than defaulting to `1:254`.
- Auto-reset the cloud-side desired count when the pool becomes `STATE_UNHEALTHY`, so growing workloads do not depend on a manual CLI step.

## Customer updates (P1, every 4 hours)

Hypothetical comms. No real customer received these.

**T+0:**

> We're investigating pending pods that are not triggering a CMK scale-up. This is not yet classified as a full cluster outage; we're checking whether a node pool is in `STATE_UNHEALTHY` and whether the autoscaler is aborting `IncreaseSize`. Please send the cluster name, the pool name, `crusoe kubernetes nodepools list` output, and recent autoscaler logs from `crusoe-system`. Next update in 4 hours, or sooner if we have a workaround.

**T+4:**

> This matches a documented CMK autoscaler limitation: when a pool's desired count is higher than Crusoe can provision, the pool goes `STATE_UNHEALTHY`, the autoscaler pins its internal target to the running count, and further `IncreaseSize` calls are silently aborted. Workaround: reset the pool with `crusoe kubernetes nodepools update <pool> --count <actual-running-count>` and wait for `STATE_RUNNING`. After it recovers, we can look at quota, regional capacity, and whether `--nodes` lists every pool. Next update in 4 hours, or sooner after the reset.

**T+8 (mitigated):**

> The scale-up block is consistent with the unhealthy-pool deadlock in Crusoe's public autoscaler article, not with a dead cluster. Please keep the count reset in place and review `--nodes` so a pool cannot grow past known capacity. We're closing this P1 and asking engineering to consider a clearer signal and an automatic count reset. If pods stay pending after the pool is `STATE_RUNNING`, we will reopen.

## Lessons

- "Autoscaler is broken" often starts as an unfulfillable desired count, not a crashed controller.
- Health of the cluster is not the same as health of one pool. Check whether a healthy pool is being shadowed.
- The recover command is a count reset, not a redeploy of the autoscaler. Try that before restarting pods.

No lab spend. This issue was not reproduced.
