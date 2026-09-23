# Threat model for the assurance engine

The trust boundary is the one 2.0 already states in [LIMITATIONS](../v2/LIMITATIONS.md):
one trusted OS user on a local filesystem. An administrator who can rewrite the SQLite
file and rebuild its hash chain is outside it. What follows is about the surface the
assurance engine itself adds, and what stops an agent — or a careless change — from
getting more claimed than was proven.

Every row below has at least one test that performs the attack for real. The test names
are in `tests/control/test_assurance_failures.py`, `_scenarios.py` and `_edges.py`.

| Attempt | What stops it | Where it is tested |
|---|---|---|
| Remove an obligation | A recompile can never drop one; the plan record lists what it held, and the integrity check reports any obligation a plan recorded that is gone from the store | `test_scenario_6_recompiling_never_drops_or_weakens_a_recorded_obligation`, `test_deleting_an_obligation_behind_the_engine_is_reported_by_the_integrity_check` |
| Mark optional what was mandatory | `monotonic` merges upward only; `contraction` names every way of asking for less, the refusal is recorded on the plan and written to the audit chain | `test_scenario_6_a_weaker_recompiled_obligation_is_refused_and_recorded`, `test_every_way_of_asking_for_less_is_named` |
| Lower a criticality, or drop a capability | Same merge: criticality rises, capabilities union, depth never falls | `test_merging_a_recompiled_obligation_can_only_ask_for_the_same_or_more` (property, 200 cases) |
| Choose a weaker verifier | Deterministic dominance, at selection and again at resolution: judgment evidence does not close a claim a declared deterministic verifier can reach | `test_scenario_8_*`, `test_judgment_never_closes_a_claim_a_deterministic_verifier_could_reach` (property) |
| Submit fabricated evidence | Evidence is only written by `verify()`, from a process the owner approved by exact argv, under a held lease. No interface accepts a claimed result | `test_a_worker_cannot_reach_the_owner_side_of_assurance`, `test_mcp_offers_the_read_and_verify_tools_and_hides_the_owner_ones` |
| Edit the stored result to say `PASS` | The verdict is checked against the run's own hashed artefact, which the row cannot change without breaking its hash | `test_relabelling_a_stored_result_as_pass_does_not_restore_the_claim` |
| Rewrite or delete an evidence artefact | The artefact hash is part of currency; either way the claim stops being supported | `test_a_rewritten_evidence_artefact_stops_proving_its_claim`, `test_a_deleted_evidence_artefact_stops_proving_its_claim` |
| Reuse stale evidence | Currency is the per-obligation binding: paths, requirement versions, protected tree, acceptance text, selected verifiers, claim text and policy | `test_scenario_3_*`, `test_staling_the_only_proof_cannot_leave_an_obligation_verified` (property) |
| Change the verifier configuration before executing | The binding covers the selected verifiers, so moving them invalidates the proof bound to them | `test_changing_the_declared_verifiers_invalidates_the_proof_bound_to_them` |
| Weaken the tests so an obligation passes | Test files are inside the claim's binding, so editing them stales the claim and forces a rerun against what is now there | `test_editing_the_tests_a_claim_rests_on_stops_it_being_proven` |
| Suppress a failure by running again | All current evidence is read together; a later `PASS` beside a current `FAIL` is `CONFLICTED`, never `PASS` | `test_scenario_7_*`, `test_a_later_pass_does_not_bury_a_current_failure`, `test_a_current_failure_never_leaves_an_obligation_verified` (property) |
| Escalate away from a failure | Escalation triggers only on `UNKNOWN` and `BLOCKED` — a route that reached no verdict. A `FAIL` means repair, and no route change can move off it | `ESCALATES` in `service.py`, `test_scenario_9_*` |
| Contract the assurance scope | Only an owner waiver, with a recorded reason and authority, and refused outright while current evidence refutes the claim | `test_scenario_6_only_an_audited_waiver_can_close_an_obligation_without_proof`, `test_scenario_6_a_waiver_cannot_hide_a_current_failure` |
| Waive without saying why | Both a reason and an authorization are required, and a waiver with neither is reported by the integrity check | `test_a_waiver_needs_both_a_reason_and_the_authority_behind_it`, `test_a_waiver_without_a_recorded_reason_is_reported` |
| Tamper with the obligation status | The persisted status is only ever an owner state; anything else is reported | `test_a_forged_obligation_status_is_reported_by_the_integrity_check` |
| Make judgment evidence look deterministic | The evidence class is stamped from the registry by the run, and the integrity check reports a judgment verdict labelled deterministic | `test_judgment_evidence_relabelled_as_deterministic_is_reported` |
| Complete while a claim is open | `complete()` reconciles against the real diff and refuses on mandatory proof debt, on every interface | `test_scenario_12_no_interface_completes_a_task_holding_mandatory_proof_debt` (service, API, CLI, MCP) |
| Let a completed task keep its claim after the code moves | The integrity check reports a completed task holding mandatory proof debt, and 2.0's invalidation already moves it to `NEEDS_REVALIDATION` | `test_a_completed_task_that_later_loses_its_proof_is_reported` |

## What an agent is allowed to do

A worker over MCP can read the assurance state, explain a claim, read the proof debt, and
run `assurance_verify` — which executes verifiers the owner already approved by exact argv,
under a lease it holds, inside the scope and budgets its contract declares.

It cannot compile or reconcile a plan on its own authority, waive a claim, record a human
verdict, register a verifier capability, migrate the project, or roll a migration back.
Those are owner operations and are not offered over MCP at all.

This preserves the principle the engine is built on: **an agent may discover that more
assurance is needed; it may never decide that less is.**

## What this does not defend against

- An administrator who edits the SQLite file and rebuilds the audit chain. Audit hashes
  detect accidental or uncoordinated tampering, not a rebuild.
- A verifier that lies. The engine proves that a command the owner approved ran, with what
  exit code, over which measured inputs. What the command asserts is the project's
  responsibility, and 2.0's verifier sensitivity and integrity audit remain the tools for it.
- External state a source fingerprint cannot see: a database, a clock, the network, an
  installed dependency, an excluded cache. A claim that depends on those needs an
  environment-specific verifier and a fresh run, exactly as in 2.0.
- Anything outside the local trust boundary. This is not an OS sandbox.
