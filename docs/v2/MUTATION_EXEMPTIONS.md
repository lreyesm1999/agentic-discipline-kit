# Verified equivalent mutants

Mutants listed here change the source without changing any behaviour a test can
observe. Each entry states the proof, so the claim can be rechecked rather than
trusted. A mutant belongs here only after the argument below has been confirmed
against the running code; everything else stays on the kill list.

This file records findings. It is not consumed by `scripts/mutation_gate.py`,
which still fails on every survivor.

## `bootstrap.initialize_project` — mutants 152, 154

```python
if isinstance(gate, dict) and str(gate.get("note", "")).startswith("added by init")
```

The mutants make the default `None` (`gate.get("note", None)`, and the same by
removing the argument). For a gate carrying no note the original evaluates
`str("")` and the mutant `str(None)`, so the comparison is `"".startswith(...)`
against `"None".startswith(...)`. Neither string starts with `added by init`, so
both yield `False` for every input, and `baseline` is unchanged. Equivalent.

## `control.verification.verify` — mutants 70, 71, 72

```python
require(not task.get("active_run"), "VERIFICATION_BUSY", "A verifier is already running")
```

The mutants read another key (`task.get(None)`, `"XXactive_runXX"`, `"ACTIVE_RUN"`),
so this first guard no longer sees a run in flight and the call proceeds. It is
then refused by the identical guard at the top of the transaction that starts a
run, which re-reads the task and raises the same code and message. Verified by
applying each mutation with bytecode caching disabled: the refusal still arrives,
raised at the second guard, with `VERIFICATION_BUSY` and the same text. No caller
can distinguish the two, so nothing observable changes.

The second guard is not equivalent: mutating its key, code or message is caught
by `tests/control/test_verification_busy.py`.

## `control.plane.Plane.create_task` — the server-owned field guard

```python
task_contract(contract)
require(
    not ({"state", "version", "id", "workspace_id", "integration"} & contract.keys()),
    "INVALID_TASK",
    "Execution state is server-owned",
)
```

`task_contract` runs first and already refuses any key outside the contract
(`data.keys() <= required | {"assumptions", "capabilities", "priority"}`), with a
different message: `Execution state is server-owned; only contract fields are
accepted`. Calling `create_task` with each of the five fields returns that longer
message, so the guard below it never runs. Every mutant on it — the five renamed
set members, their upper-case variants, and the code and message swaps — changes
a line no caller can reach.

The rule itself is covered: `tests/control/test_contract_rules.py` asserts the
`task_contract` refusal by exact code and message.

## `verifier.executor.execute_verifier` — the `working_directory` and `expected_exit_code` defaults

```python
working_directory = str(metadata.get("working_directory", "."))
expected = int(metadata.get("expected_exit_code", 0))
```

Both keys are `required` in `schemas/verifier.schema.json`, and `load_verifier`
validates the contract on every call through `load_and_validate_verifier`. Removing
either key from a registered package and running the verifier is refused with
`invalid verifier contract: $: '<key>' is a required property`, before either
default is read. The mutants that change those defaults (to `None`, to a removed
argument, or to another value) therefore change unreachable code.

## Known survivors, not exempt: `Plane._expire` boundaries

```python
if lease["state"] == "ACTIVE" and lease["expires_at"] <= time.time():
    ...
    and running.get("active_run_deadline", 0) > time.time()
```

Three mutants here are not killed by `tests/control/test_lease_lifecycle.py`, and
none of them is listed as equivalent. Turning `<=` into `<` matters only for a
lease expiring at exactly the current instant; raising the deadline default from
`0` to `1` matters only when the key is missing *and* the deadline is `1`; turning
`>` into `>=` matters only at the same single instant. Each is reachable in
principle by forcing a timestamp, and unreachable in any run a reader would
recognise. They stay on the kill list, unkilled.

The rest of the sweep is covered: skipping a lease held by a running verifier
without ending the sweep, and expiring every lease that ran out.

## Known survivor, not exempt: `Plane.context` evidence default

```python
if evidence["task_id"] == task_id and evidence["finished_at"] > latest_evidence.get(
    evidence["verifier"], {}
).get("finished_at", 0):
```

The mutant raising that `0` to `1` is not listed above, because it is not proven
equivalent. The default applies only to the first record seen for a verifier, so
the two values differ only for a record whose `finished_at` is exactly `1` — one
second after the epoch. A forced record would distinguish them, so a test could
exist; it would assert nothing a reader would recognise as behaviour. It stays on
the kill list, unkilled, rather than being written off.

The neighbouring mutants are killed by `tests/control/test_context_evidence.py`:
reading another key, or stopping the scan at the first passing verifier.

## Method

Apply the mutation to the source, clear `__pycache__` and run with `-B`
(`PYTHONDONTWRITEBYTECODE=1`), then run the tests that cover the line. Every
mutation used here is length preserving, so a cached `.pyc` written in the same
second will silently run the unmutated code and report a false survivor.
