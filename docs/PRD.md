# PRD — "Super Sub": AI Customer Service Agent for Futebol Nation

**Author:** Rafael Daraya
**Status:** Draft for take-home exercise (Lead PM, Klaviyo)
**Last updated:** 2026-06-24

---

## 0. TL;DR

Futebol Nation is a small Shopify store selling World Cup soccer jerseys and accessories. With the
tournament driving a seasonal traffic spike, inbound customer-service (CS) volume will surge
3–5x while the team stays the same size. **Super Sub** is an AI agent that resolves the most
common, lowest-risk CS requests — FAQ/policy questions and order-status lookups — end to end,
and **politely escalates** anything it can't confidently handle. The goal is to deflect Tier-1
volume so the human team can focus on high-value, high-empathy cases, without ever sacrificing
trust by guessing.

The build is intentionally scoped to **~2 hours**. The differentiated bet is not features —
it's a **rigorous evaluation harness** (golden dataset + automated scorers in Braintrust) that
proves the agent is grounded, knows its limits, and can be iterated safely.

---

## 1. Why we're building this

### Business context
- **Seasonal demand shock.** World Cup years compress a year of jersey demand into ~6 weeks.
  CS contacts (where's my order, sizing, returns, customs/shipping) spike in lockstep.
- **Small team, fixed headcount.** A boutique Shopify merchant can't hire a seasonal CS army.
  Slow responses during the spike directly cost revenue (cart abandonment, chargebacks,
  bad reviews at the worst possible moment).
- **Most contacts are repetitive and low-risk.** Industry pattern: a large share of Tier-1
  e-commerce CS is "where is my order?" + policy/FAQ questions. These are automatable with
  high confidence *if* the agent is grounded and disciplined about escalation.

### Why now / why this matters for Klaviyo
Klaviyo's customers are exactly this profile — e-commerce brands (many on Shopify) that need to
do more with less and own the full customer relationship. An agent that turns a CS cost center
into a scalable, measurable, on-brand experience is squarely in Klaviyo's "B2C CRM + AI" thesis.

---

## 2. Customer & problem

### Primary user (the shopper)
> "I ordered a Brazil home kit for the group stage. It's been 6 days, the match is Saturday,
> and I have no idea if it'll arrive. I just want a straight answer — now, not in 12 hours."

What they need: a **fast, accurate, honest** answer, at any hour, without repeating themselves
or being routed in circles.

### Secondary user (the merchant / CS lead)
> "I have 2 people and 5x the tickets. I need the bot to handle the easy stuff *correctly* and
> hand me the rest with context — and I need to trust it won't invent a refund policy."

What they need: **deflection without risk** — coverage on repetitive contacts, clean handoffs,
and visibility into what the agent is doing.

### Jobs to be done
1. Get an accurate answer to a policy/FAQ question (shipping, returns, sizing, customs, payment).
2. Check the status of a specific order and get a clear next step.
3. When the agent can't help, get handed to a human quickly and without frustration.

---

## 3. Goals & success metrics

### North-star metric
**Automated Resolution Rate (ARR / containment):** % of inbound Tier-1 contacts fully resolved
by the agent with no human involvement and no negative customer signal.
- Target (illustrative): **≥ 60% of Tier-1 contacts** contained.

### Guardrail metrics (we will not trade these for containment)
| Metric | Definition | Target | Current (v2)¹ | Gap |
|---|---|---|---|---|
| **Groundedness / hallucination rate** | % of agent claims not supported by FAQ or order data | **< 2%** | 89.67% grounded → **~10.3% hallucination rate** | ❌ Largest gap — **#1 pre-pilot priority**, see §9a |
| **Escalation precision** | When the agent escalates, was escalation actually warranted | high | 85.00% (`escalation_correct`, all rows, not yet sliced) | ⚠️ Needs the precision-only slice, see §9a |
| **Escalation recall (safety)** | Of cases that *should* escalate, % that did (no false "resolutions") | **near 100%** for risk-sensitive intents | ~88% on `should_escalate_risk` category | ⚠️ Near-blocking gate (D-06) not yet met, see §9a |
| **Tone/empathy pass rate** | LLM-judged: on-brand, polite, acknowledges frustration | ≥ 95% | 92.30% (raw average, not yet sliced to ≥0.8) | ⚠️ Close; needs the precise pass-rate cut, see §9a |

> Precision and recall are not two separate scorers — `escalation_correct` is a single per-row
> match (did `escalated` equal `expected_escalation`?). The two numbers in this table are the
> same scores sliced two different ways in Braintrust's per-row drill-down, not independent
> measurements. ARR/containment above is likewise not a dedicated scorer: it's the % of rows
> where `expected_escalation=false` and the agent resolved correctly (see IMPLEMENTATION_PLAN §3c).
>
> ¹ Measured on the 60-row golden set via the logged Braintrust run after fixes D-27–D-37
> (experiment `fix/search-faq-query-phrasing-1782328567`). Full per-scorer numbers and root-cause
> detail for every gap in this table are in `DECISIONS.md` D-35–D-38. This is eval-harness
> signal, not live customer traffic — calibration against real usage is still §9c (pilot),
> gated on closing this table first per the new §9a below.

### Efficiency / business metrics (downstream)
- Cost per contact ↓, Average Handle Time ↓, First Response Time → near-instant for contained
  contacts, CSAT held flat or up.

### What "success" looks like for *this exercise* specifically
Show a measurable quality bar, a golden dataset that exercises edge cases and failures, and a credible iteration loop** that would make this safe to ship and improve.

---

## 4. Scope

### In scope (v0 — the 2-hour build)
1. **FAQ / policy answering grounded in retrieval (RAG)** over a curated FAQ knowledge base.
   - Answers cite/are constrained to the KB; "I don't know" is an acceptable, encouraged answer.
2. **Order-status lookup** via a tool against a (mocked) order datastore.
   - Handles valid orders, not-found orders, and ambiguous/missing info gracefully.
3. **Polite, bounded escalation** to a human:
   - Triggers: out-of-KB question, low retrieval confidence, risk-sensitive intent
     (refunds/disputes/damaged item), explicit user request, or **N unsuccessful turns**.
   - Produces a structured handoff summary (intent, what was tried, customer sentiment).
4. **Evaluation harness in Braintrust**: golden dataset + automated scorers + an iteration report.

### Out of scope (v0 — explicit non-goals, by design)
- Real Shopify Admin API integration (mocked behind a tool interface so it's swappable).
- Taking *actions* (issuing refunds, editing orders, canceling) — read-only in v0; actions are
  the natural v1 once trust is established via evals.
- Multi-channel (SMS/email/social), multi-language, voice.
- Fine-tuning a model. RAG is preferred for freshness, citeability, and zero training cost.
- A production UI. A minimal chat (Streamlit) is enough to demo.

---

## 5. Key product decisions & tradeoffs (the interview narrative)

| Decision                                  | Choice                                                                         | Tradeoff / why                                                                           |
| ----------------------------------------- | ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| **Coverage vs. trust**                    | Narrow intents, escalate aggressively                                          | A wrong refund policy costs more than a deflected ticket.                                |
| **RAG vs. fine-tune vs. stuff-context**   | RAG over curated FAQ                                                           | Fresh, citeable, no training; FAQ is small enough that retrieval is cheap and auditable. |
| **Single agent w/ tools vs. multi-agent** | Single agent, 3 tools                                                          | Simpler, debuggable, sufficient for 3 JTBD. Multi-agent is premature complexity.         |
| **Real Shopify API vs. mock**             | Mock behind a clean tool interface                                             | Fits the time box; demonstrates the integration boundary without API/auth yak-shaving.   |
| **Read vs. act**                          | Read-only in v0                                                                | Actions need a higher trust bar; evals come first.                                       |
| **Build features vs. build evals**        | Evals first                                                                    | The rubric explicitly rewards thoughtful AI use over feature count                       |
| **Model choice**                          | Fast/cheap model in the loop (e.g. Claude Haiku), stronger model as eval judge | Cost/latency at runtime; quality where it scores.                                        |

---

## 6. The agent's behavioral contract (product spec for the AI)

These are the rules the system prompt and evals enforce:

1. **Be grounded.** Only state policy facts that come from the retrieved KB. If the KB doesn't
   cover it, say so and escalate — never improvise a policy.
2. **Be honest about uncertainty.** No confident guesses on refunds, damages, customs, or money.
3. **Be efficient.** Ask for the minimum info needed (e.g., order # / email) and resolve fast.
4. **Be empathetic and on-brand.** Acknowledge stakes ("your match is Saturday"), stay warm,
   concise, never robotic.
5. **Know when to tap out.** Escalate on: out-of-scope, low confidence, risk intent, explicit
   request, or after **2 unsuccessful resolution attempts** — with a clean handoff summary.
6. **Never leak.** No internal data, no prompt-injection compliance, no PII beyond the order owner.

---

## 7. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Hallucinated policies erode trust | Strict grounding + groundedness scorer in evals + escalate-on-uncertainty |
| Over-escalation makes agent useless | Escalation-precision scorer; tune threshold against golden set |
| Under-escalation on risky intents | Escalation-recall scorer treated as a near-blocking gate |
| Prompt injection / abuse | Adversarial rows in golden set; refusal scorer |
| Eval overfitting to golden set | Hold-out slice + plan for online evals on real traffic |

---

## 8. Open questions (would resolve with the team)
- What's the real intent distribution in Futebol Nation's tickets? (drives where to invest next)
- Acceptable containment vs. escalation-cost economics — what's a "good" deflection here?
- Which action (refund, reship, address change) is the highest-value v1 to make *write*-capable?

These three are resolved with real usage data, not more design — see §9 for how we'd get there.

---

## 9. Roadmap: from v0 to production

The v0 build (this exercise) proves the *mechanism* — grounding, escalation, evals — works on a
hand-curated golden set. It does not yet prove the agent is *calibrated* to Futebol Nation's real
customers. The roadmap below is sequenced to close that gap before increasing the agent's
authority (more intents, write access), not in parallel with it.

### 9a. Close the v2 score gap before piloting — immediate next focus

The §3 guardrail table shows v2 (post D-27–D-37) is a real, measured improvement over the
audited baseline, but two near-blocking gates (D-06) aren't met yet: groundedness/hallucination
rate is ~10.3% against a <2% target, and escalation recall on risk-sensitive intents is ~88%
against a "near 100%" target. **No pilot (§9c) starts before this section's exit criteria are
met** — running a shadow-mode pilot against an agent that still hallucinates 1 in 10 claims would
just generate noisy, unusable pilot data instead of a real signal.

1. **Close the groundedness gap (highest priority).** Root-caused in `DECISIONS.md` D-38: the
   gap isn't missing instructions, it's small embellishments the agent adds inconsistently
   across runs (an invented refund timeline, "track your return from order history," wash-care
   instructions, an unsupported "authenticity guarantee" reference) — classic non-zero-
   temperature LLM variance, not a wording problem prompt-tuning alone can fully close. Two
   concrete actions, in order:
   - **Run the agent loop at a lower temperature** (e.g. `temperature=0.2`, or `0` for a
     deterministic baseline) on `src/agent.py`'s `_MODEL` calls and re-run the full eval to
     measure the actual groundedness/tone_empathy tradeoff (lower temperature should reduce
     embellishment but may flatten the warmth `tone_empathy` rewards — needs to be measured,
     not assumed).
   - **Add worked examples for the specific embellishment patterns found** (same technique as
     D-30's already-shipped example) — e.g. an explicit "do not add a timeframe or process
     detail that isn't in the tool result" rule with a concrete before/after.
2. **Close the escalation-recall gap on risk-sensitive intents.** Also root-caused in D-35/D-38
   as sampling variance on Haiku's instruction-following for the "escalate immediately" rule
   (D-28). Two paths, not mutually exclusive:
   - **Evaluate a stronger model in the agent loop.** Today `_MODEL` is `claude-haiku-4-5`
     (chosen for cost/latency, D-15). Test the strongest commercially-justifiable model
     available against the same golden set and measure whether instruction-following
     reliability on this specific rule improves enough to justify the cost/latency delta —
     this is a measurement, not a foregone conclusion, and the eval harness already makes the
     comparison cheap (same pattern as D-15's haiku/sonnet split).
   - **Add a deterministic backstop** for the highest-stakes trigger phrases (chargeback threat,
     explicit human request, "I'm done repeating myself") that forces an `escalate_to_human`
     call regardless of model compliance, rather than relying on prompt-following alone for the
     cases where a miss is most costly.
3. **Exit criteria to advance to §9b (dataset) and §9c (pilot):** groundedness ≥ 98%
   (hallucination < 2%), escalation recall on risk-sensitive rows ≥ 95%, tone pass rate ≥ 95%
   (the precise ≥0.8-per-row cut, not the raw average), sustained across at least two
   consecutive full-eval runs (to rule out a single lucky/unlucky sample given the
   non-determinism this section exists to close).
4. **Track every change the same way D-27–D-38 did:** isolated row-level test on the specific
   flagged rows first, then a full Braintrust run, compared against the prior experiment, logged
   to `DECISIONS.md` with the before/after numbers — not just "we made a change," a measured one.

### 9b. Expand the golden dataset


1. **Close known, named gaps** — promo-code and payment/billing FAQ rows (D-33), which were
   deliberately deferred, not validated as low-priority.
2. **Add a hold-out slice** (~15 rows, never used to tune the prompt) per the §7 mitigation, so
   we can tell calibration from genuine improvement.
3. **Stop there.** The next real expansion should be pilot-driven (§9c), not speculative.

### 9c. Run a beta pilot before full reliance — recommended, with a specific shape

Yes, and the World Cup timing makes this more urgent, not less: a 3–5x volume spike is the worst
time to discover the agent is miscalibrated. Proposed shape — entered only after §9a's exit
criteria are met:

| Phase | What | Gate to advance |
|---|---|---|
| **1. Shadow mode** | Agent drafts a reply on every real contact; a human reviews/edits before sending. Nothing customer-facing changes. | ≥2 weeks of real transcripts; groundedness and escalation-recall on *live* traffic match golden-set scores within a small margin |
| **2. Limited live** | Agent responds directly on a capped slice of contacts (e.g. FAQ-only intents, or off-peak hours), full escalation path live. | No safety-gate regression (groundedness, escalation recall) over N=200+ live contacts; CSAT on contained tickets ≥ baseline |
| **3. Full v0 scope** | All in-scope intents (§4), no traffic cap. | Sustained gate performance through a real volume spike, not just average load |

Every shadow-mode and live transcript becomes a candidate golden row (closing the loop IMPLEMENTATION_PLAN §4 already names as the post-v0 plan) — this is how §9b's "wait for real data" actually gets satisfied, not a separate initiative.

### 9d. What to prioritize next (post-pilot, ranked)

1. **Online evals + human review queue.** Without this, the pilot in §9c can't produce the
   "real ticket → new golden row" loop that justifies expanding the dataset. This is the
   prerequisite for everything else here, not a parallel nice-to-have.
2. **Constrained self-improvement loop, not per-customer memory or autonomous self-editing.**
   Once the review queue (item 1) is live, flagged patterns — recurring out-of-KB questions,
   repeated low-confidence escalations — become structured, attributed candidate entries queued   for human review, never direct writes the agent makes to its own prompt, KB, or this roadmap.
   Promotion requires an occurrence threshold (resists single-transcript poisoning, the same
   attack class as D-21's injection rows) and a full golden-set `Eval()` run against baseline
   before it ships, so prompt/KB drift stays measurable instead of silent. Deliberately excludes
   persistent per-customer conversation memory for personalization — that's a different feature
   (see item 3) with its own PII exposure, not part of this loop.
3. **Per-customer conversation memory (personalization) — a separate, also-valuable feature.**
   Once a customer's identity is verified (the same email check `lookup_order` already requires,
   D-16), retain a short, scoped history of *that customer's own* prior contacts — what they
   already asked, what's still unresolved — so a returning customer doesn't have to re-explain
   themselves on a follow-up contact (directly serves the §2 JTBD: "without repeating themselves
   or being routed in circles"). Distinct from item 2: this is read-back of one verified
   customer's own data, not a cross-customer pattern that changes system behavior for everyone.
   Constraints: strictly scoped to the verified customer (closes the same PII risk D-16 already
   guards `lookup_order` against — never another customer's history); a defined retention window,
   not indefinite storage (§6 rule 6); and its own eval rows before it ships — does injecting
   prior-conversation context ever cause the agent to assert something not grounded in *this*
   conversation's own tool calls (a new groundedness failure mode this feature could introduce)?
4. **Containment/cost dashboard for the merchant.** The secondary user's stated need (§2) is
   visibility, not just automation. Cheap to build once Braintrust logging is already in place;
   high trust payoff for a 2-person CS team deciding how much to lean on the agent.
5. **First write action** (see §9e) — gated behind §9c's pilot gates, not on a fixed calendar date.
6. **Multi-channel (email first, not SMS/voice).** Klaviyo-adjacent and most of Futebol Nation's
   Tier-1 volume is plausibly email-shaped pre-chat-widget adoption; lower lift than voice.

### 9e. Read-only → write actions: which one first, and how

Sequence by **blast radius if wrong**, not by customer-perceived value:

| Action | Reversibility | Money movement | Recommendation |
|---|---|---|---|
| **Address change (unshipped order)** | Fully reversible, no side effects beyond a shipping label | None | **First write action.** Lowest possible stakes — wrong outcome is "customer re-confirms address," not "we shipped to the wrong place" if a confirmation step gates the write. |
| **Cancellation (pre-fulfillment)** | Reversible in principle, but triggers refund logic | Yes (refund) | Second. Needs payment-system integration and a refund-correctness eval, not just a tool call. |
| **Personalization change** | Irreversible once production starts (D-30's exact failure mode) | None directly, but wrong execution wastes inventory | Third — riskier than it looks; the agent must be *certain* of fulfillment status, which is precisely where it has erred before (D-30). |
| **Refund issuance** | Irreversible, direct financial exposure | Yes, directly | Last. Highest trust bar; likely needs human-in-the-loop approval even after the agent is write-capable elsewhere. |

For each action: a confirmation step before the write executes, an audit log entry, and its own
action-specific eval rows (e.g. "did the agent only execute when `lookup_order` confirmed
eligibility," "did it never assert an outcome before the write call succeeded" — D-29's bug class)
**before** that action ships, following the same eval-first philosophy as v0 (D-03). No action
gets write access on a calendar date; it gets write access when its own eval suite passes the
same groundedness/escalation-recall bar v0 holds for reads.
