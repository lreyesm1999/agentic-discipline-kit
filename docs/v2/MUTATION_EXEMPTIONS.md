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

## `acceptance.parse_feature_text` — the pending scenario id sentinel

```python
pending_id: str | None = None
...
"id": pending_id or f"AC-{len(scenarios) + 1:03d}",
```

The mutants make that sentinel `""` instead of `None`. The value is only ever
tested for truthiness, and both are falsy, so a scenario without a declared id
still gets the generated one. `pending_id` is never compared with `is None` or
with a string, so no caller can distinguish the two.

## Measured, not argued: defaults the suite never falls back to

A `.get(key, default)` mutant can only be observed when the key is missing. Rather
than arguing case by case, every two-argument `.get` call in the package was
rewritten to record when it actually used its default, and the whole suite was run
against the instrumented tree. Of 73 real mapping defaults, 53 were used at least
once and **20 were never reached in 1250 tests**; those sites carry 39 catalogued
survivors. The recording is evidence, not proof: it shows the current suite cannot
reach them, which is exactly what makes those mutants survive.

Two cautions came out of that run, and both matter for anyone repeating it:
`Store.get(identifier, kind)` is a method, not a mapping, so its two-argument
calls are not defaults at all and must be excluded — 78 catalogued survivors are
that type guard, and they are killable (`tests/control/test_record_kinds.py`
kills thirteen). And 5 of 1255 tests failed under instrumentation, so the
rewritten tree is not perfectly faithful; the mapping results were unaffected but
the tool is not clean.

## Equivalent where the measurement runs: the dropped `encoding` argument

```python
path.write_text(content, encoding="utf-8")
path.read_text(encoding="utf-8")
```

Mutants that drop the argument or set it to `None` fall back to the platform's
preferred encoding. On the Linux environment the mutation campaign runs in,
`locale.getpreferredencoding(False)` is `UTF-8`, so the mutated call reads and
writes exactly the same bytes and no test can separate them. Roughly thirty
catalogued survivors are this shape.

This is an equivalence of the measuring environment, not of the code: on a
machine whose preferred encoding is not UTF-8 — a Windows console default of
cp1252, or a container with a POSIX locale — the same mutation would corrupt
non-ASCII content. The explicit `encoding="utf-8"` in the source is what prevents
that, and the Windows jobs in the platform matrix are what exercise it. Keep the
argument; do not treat these survivors as a reason to remove it.

## Equivalent by the language: three families

Each rule below is a property of Python itself, checked by running it, so it holds
for every site of that shape rather than needing an argument per mutant.

**`typing.cast` type argument.** `cast(T, value)` returns `value` unchanged at
runtime and never inspects `T`. Mutating the type argument, including to `None`,
cannot change what the call returns. Checked: `cast(None, value) is value` and
`cast(list[int], value) is value` are both true.

**Codec name case.** `"utf-8"`, `"UTF-8"` and `"Utf-8"` resolve to the same codec
through `codecs.lookup`, so flipping the case of an explicit encoding name cannot
change a single byte read or written. This is distinct from dropping the argument,
recorded above, which is only equivalent where the platform default is UTF-8.

**Pattern case under `re.IGNORECASE`.** When a pattern is matched with
`re.IGNORECASE`, changing the case of its literal characters cannot change what it
matches or what its groups capture. Checked on the Gherkin patterns with lines in
upper, lower and mixed case, plus a line that must not match: every pair matched
identically and captured identical groups. A mutant that *removes* the flag is not
in this family; it changes behaviour and stays on the kill list.

## Equivalent by SQLite: case in keywords and identifiers

```python
self.store.db.execute("select * from edges where source=? and target=? and relation=?", ...)
```

SQLite treats SQL keywords and unquoted identifiers — table and column names —
without regard to case, so `select * from edges` and `SELECT * FROM EDGES` are the
same statement. Checked by running four case variants of one query against a real
table: every variant returned the same rows.

The rule has a boundary, and it was checked mutant by mutant: SQLite does **not**
ignore case in *values*. `WHERE kind='TASK'` does not match a row whose kind is
`task`. So a mutant belongs in this family only if every single-quoted literal in
the statement is unchanged. All catalogued SQL survivors were compared on exactly
that: none changes a quoted value; each changes only keywords or identifiers.

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
