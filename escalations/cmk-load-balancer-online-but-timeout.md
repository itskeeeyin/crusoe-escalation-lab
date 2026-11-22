# Example escalation: CMK load balancer shows backends Online, client requests time out

This is an example customer escalation built from a **public Crusoe Support how-to**. It is **documented, not reproduced**. This lab did not create a CMK cluster, Service, or load balancer. The customer name and any dollar impact below are **hypothetical**.

Suggested severity: **P1**, customer updates **every 4 hours**. User-facing traffic is failing while the load balancer health view looks healthy, which delays detection. Existing cluster compute may still be fine, so this is not automatically a P0. Use P0 (hourly updates) if this is a production entry point with no alternate path.

## Source (real public report)

Crusoe Support, "How-To Manage Load Balancer Firewall Rules Automatically on CMK," updated 29 September 2026:

https://support.crusoecloud.com/hc/en-us/articles/54052858599963-How-To-Manage-Load-Balancer-Firewall-Rules-Automatically-on-CMK

The article states: "Crusoe Cloud load balancers are Layer 4 pass-through: they forward connections to your backends, but creating one does not open any firewall path to those backends. On CMK, the backends are your worker nodes' NodePorts, so a new `type: LoadBalancer` Service needs an ingress rule for its NodePort before any client traffic can arrive."

The sharp edge: "Load balancer health checks originate on the infrastructure side and do not traverse your firewall rules, so every backend can show `Online` while 100% of real client traffic is dropped. A missing firewall rule is the most common reason a brand-new load balancer "doesn't work"."

The worked example in the same article is the same symptom: "A team exposes an inference endpoint through a `type: LoadBalancer` Service on CMK. The load balancer provisions, every backend shows `Online`, and client requests still time out. The cause is the classic one: no ingress rule for the NodePort, invisible to health checks."

The documented workaround is the opt-in annotation `crusoe.ai/manage-firewall-rule: "true"` on the Service (controller v0.0.23 or later), plus `loadBalancerSourceRanges`. Omitting source ranges "defaults to 0.0.0.0/0 and your NodePort is reachable from the entire internet." Custom VPCs also have no default firewall rules; that implicit deny is documented at https://docs.crusoe.ai/networking/firewall-rules/overview/.

## Customer symptom

Hypothetical customer: they created a `type: LoadBalancer` Service for an inference or web app on CMK. The Service gets an external IP, every backend is `Online`, and `kubectl get svc` looks healthy. Clients time out. They open a P1: "the load balancer is broken" or "Crusoe networking is dropping our traffic."

## Reproduction status

**Documented, not reproduced.** No load balancer, Service, or firewall rule was created on this account. Evidence below is the public article and firewall overview only.

A paid sitting was authorized on 21 November 2026 at 7:18 PM PT (America/Los_Angeles) to execute `PAID_SESSION_PLAN.md`. It stopped immediately: `crusoe whoami` returned HTTP 401 / failed to authenticate user. The Cloud CLI access key in the environment was the same string as the Intelligence API key, which is a different credential type. No create commands were issued. See [`SESSION_LOG.md`](../SESSION_LOG.md).

## Hypotheses and tests

| ID | Hypothesis | Test | Result |
| --- | --- | --- | --- |
| H1 | The Service never provisioned an external IP, or the controller is down | `kubectl get svc`, `helm list -n crusoe-system`, controller logs | Not run here. A provisioned IP with Online backends is the documented trap, not a missing IP. |
| H2 | No ingress firewall rule exists for the Service NodePort, so client traffic is dropped while health checks still pass | `kubectl get svc` for the NodePort; `crusoe networking vpc-firewall-rules list` for that port | Not run here. This is the cause named in the article. |
| H3 | The cluster is in a non-default VPC with no default allow rules | Confirm VPC and whether any ingress rule includes the NodePort | Not run here. Public firewall docs say custom VPCs start with implicit deny. |
| H4 | The controller tried to create a rule or a load balancer and hit `403 Forbidden` (quota) or a typo'd annotation | Controller logs for `403`, `firewall`, and `rule`; confirm the annotation is exactly `crusoe.ai/manage-firewall-rule="true"` | Not run here. The article separates "silent grep with no matching lines" (annotation never seen) from `ERROR` (it tried and failed). |
| H5 | A previous unmanage-then-delete left an unexpected rule, or a broad manual rule is masking the managed one | List rules; check `crusoe.ai/firewall-rule-id` | Not run here. The article warns about orphaned world-open rules and union-of-rules masking. |

## Workaround

- Confirm the NodePort from `kubectl get svc` and look for an ingress rule whose destination is that port. If it is missing, this is the documented cause.
- Short-term: add an ingress rule for that NodePort, scoped to the client CIDRs you actually intend to allow. Do not open all ports to `0.0.0.0/0` as a standing fix.
- Lasting: install or confirm the Crusoe Load Balancer Controller at chart 0.0.23 or later, annotate the Service with `crusoe.ai/manage-firewall-rule=true`, and set `loadBalancerSourceRanges` to office or VPN CIDRs. The article says the rule usually appears within a minute and can be added to an existing Service without recreating the load balancer.
- After it works, `nc -zv <EXTERNAL_IP> <PORT>` from an allowed source, and from a denied source, so you do not confuse "open to the world" with "fixed."
- If controller logs show `403 Forbidden` while creating the load balancer itself, treat it as exhausted load-balancer quota, not a firewall miss.

## Long-term fix and engineering ask

Practice recommendations, not a claim about Crusoe's roadmap:

- Warn in the Console when a load balancer has Online backends but no ingress rule covers the NodePort.
- Consider making firewall management the default for new `type: LoadBalancer` Services, still requiring an explicit source range so the default is not `0.0.0.0/0`.
- When health checks bypass customer firewall rules, say that in the load-balancer status view, next to `Online`.

## Customer updates (P1, every 4 hours)

Hypothetical comms. No real customer received these.

**T+0:**

> We're investigating client timeouts to the new load balancer. Backends showing `Online` does not by itself prove the data path is open: Crusoe load-balancer health checks do not go through your VPC firewall rules. We're checking for an ingress rule on the Service NodePort. Please send the Service YAML, the NodePort, the external IP, and `crusoe networking vpc-firewall-rules list` for the project. Next update in 4 hours, or sooner if we have a workaround.

**T+4:**

> This matches Crusoe's documented "most common reason a brand-new load balancer doesn't work": no ingress rule for the NodePort, while health checks still report Online. Workaround: add a scoped ingress rule for that NodePort, or annotate the Service with `crusoe.ai/manage-firewall-rule=true` and set `loadBalancerSourceRanges` so the Load Balancer Controller creates the rule. Do not leave the source range at `0.0.0.0/0` unless you intend the NodePort to be public. Next update in 4 hours, or sooner after you confirm a test from an allowed CIDR.

**T+8 (mitigated):**

> The timeouts are consistent with a missing NodePort firewall rule, not with a failed load-balancer provision. Please keep the managed rule (or your scoped manual rule) in place. We're closing this P1 and asking that the Online status make the health-check versus data-path distinction clearer. If allowed clients still time out after the rule is present and active, we will reopen.

## Lessons

- `Online` on a Crusoe load balancer is not a data-path probe through the customer's firewall. Say that in the first update, before anyone spends hours on application logs.
- The fix is a NodePort ingress rule, not a new load balancer, and not a wider "allow all" rule.
- When enabling the controller, always set `loadBalancerSourceRanges`. The unsafe default is the whole internet.

No lab spend. This issue was not reproduced.
