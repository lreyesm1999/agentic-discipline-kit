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

## Method

Apply the mutation to the source, clear `__pycache__` and run with `-B`
(`PYTHONDONTWRITEBYTECODE=1`), then run the tests that cover the line. Every
mutation used here is length preserving, so a cached `.pyc` written in the same
second will silently run the unmutated code and report a false survivor.
