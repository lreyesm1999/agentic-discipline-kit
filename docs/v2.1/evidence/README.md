# Assurance engine evidence

Each file is the preserved output of a command that was actually run, in this repository,
on the revision the run records. Nothing here is inferred and nothing is edited afterwards.

| Artifact | What produced it | Reproduce with |
|---|---|---|
| `dogfood.json` | The engine applied to this repository's own 2.1 work: obligation compilation, plan creation, real pytest executions, evidence resolution, staleness and its recovery, assurance expansion, a retained obligation after the surface was removed, blocked completion, conflicting evidence on a second task, and the audited waiver that closed it | `python scripts/assurance_dogfood.py --reset --output docs/v2.1/evidence/dogfood.json` |
| `mutation.json` | A scoped mutation campaign over the assurance package, mutant by mutant, with the baseline control that proves the harness rebuilds the modules faithfully, and its gate against the reviewed dispositions | `python scripts/assurance_mutation.py --dispositions docs/v2.1/evidence/mutation-dispositions.json --journal mutation.jsonl --output docs/v2.1/evidence/mutation.json` |
| `mutation-dispositions.json` | The reviewed survivors: module, exact line source, family, count, kind (`equivalent` or `platform`) and the reason, one entry per group | Written by review; `--dispose` drafts entries for new survivors, which still need a reason |
| `benchmark.json` | The 1,000-file fixture, now measuring plan compilation, reconciliation, obligation resolution and staleness recalculation alongside the 2.0 figures | `python scripts/control_benchmark.py --files 1000 --output docs/v2.1/evidence/benchmark.json` |
| `checks.log` | The gates: lint, format, types, the full suite with coverage, the coverage gate, the repository check and the assurance integrity check | see `../VALIDATION.md` |

## Reading `dogfood.json`

`steps` is the sequence the run went through, each with the required obligation count, the
status counts, the proof debt and the decision at that moment. It is the clearest single
view of the engine: `VERIFIED` after the verifiers ran, `STALE` after a proven file moved,
`VERIFIED` again after it was restored byte for byte, `UNKNOWN` for the claim the expanded
diff raised, and `WAIVED` only after an owner recorded a reason and an authority.

`verifier_executions` names each real process, its exit code and the hashed artefact it
wrote. `blocked_completion` is the refusal, with its code and message.

## Reading `mutation.json`

`baseline` is the control: the modules rebuilt from their own syntax trees, unmutated, must
still pass the selection, or a rewriting bug would look like a suite that kills everything.
`counts` and `mutation_score` are the result; `per_module` and `per_family` say where the
strength is; `unresolved` lists every mutant the tests did not kill, with its module, line,
family and the exact before and after, so a survivor can be triaged rather than counted.
`gate` is the verdict against `mutation-dispositions.json`: the survivors it accepts, any it
does not (`unresolved_after_review`) and any entry that matched nothing (`stale_dispositions`).
`method` says whether the run was a full campaign or a `--resume` of one over identical
sources, which reruns only the positions still alive.

`why_not_mutmut` records why this is a purpose-built harness rather than the
repository-wide `mutmut` gate that CI runs. That gate is unchanged and still covers the
whole package.
