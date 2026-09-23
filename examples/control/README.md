# Control-plane examples

Replace the objective, scope, acceptance, requirement IDs, verifier commands and budgets
with the real ones for your project. An empty requirement list suits a small maintenance
change; it is not proof of traceability.

| File | What it is for |
|---|---|
| `task.json` | The smallest real task contract: one acceptance criterion, one verifier. Used by the [2.0 guide](../../docs/v2/README.md). |
| `checkpoint.json` | A truthful checkpoint, which completion requires. |
| `assurance-task.json` | A HIGH-risk change written so the assurance engine has something to work with. |

## Reading `assurance-task.json`

The contract declares six verifiers across three surfaces, and only two of them are bound
to an acceptance criterion. That is deliberate: `acceptance` and `integration` prove what
the contract promises, and `regression`, `contract`, `property` and `migration` are the
capabilities the **planner** draws on for the claims repository policy raises once the diff
is real. A verifier with an empty `acceptance` list is still required evidence and still
approved by exact argv; it is simply not tied to one criterion.

Because the scope touches `src/pnl`, `src/api` and `migrations`, the compiler raises the
money, public-interface and migration claims as soon as the diff confirms those surfaces,
and the HIGH risk adds the falsification claim. The directory is `src/pnl` rather than
`src/profit` on purpose: the compiler reads **path names**, using the same patterns
`agentic-discipline risk` uses, and `pnl` is one of the words those patterns recognise as
financial. A differently named folder raises nothing until the pattern in
`config/risk-weights.json`'s `money` signal is extended, which is the coarseness recorded
in [LIMITATIONS](../../docs/v2.1/LIMITATIONS.md). The planner then picks:

```text
acceptance criterion 0   -> acceptance          (the contract's own binding)
acceptance criterion 1   -> integration         (the contract's own binding)
financial stability      -> regression          (historical_stability, medium cost)
interface compatibility  -> contract            (contract_compatibility, low cost)
migration safety         -> migration           (data_preservation, the only kind that
                                                 declares it)
test strength            -> property            (falsification, cheaper than mutation)
```

Add a `mutation` verifier and the falsification claim escalates to it only if the property
route reaches no verdict — a cheaper falsifying route that answers is not replaced.

```sh
agentic api approve_command --input /private/command.json --json   # once per verifier argv
agentic task create --input examples/control/assurance-task.json --json
agentic assurance plan TASK-ID --compile --json
```
