# Verified equivalent mutants

Mutants listed here change the source without changing any behaviour a test can
observe. Each entry states the proof, so the claim can be rechecked rather than
trusted. A mutant belongs here only after the argument below has been confirmed
against the running code; everything else stays on the kill list.

This file records findings; `scripts/mutation_gate.py` does not read it. The gate
proves four of the families below itself, mutant by mutant, from mutmut's `mutants/`
tree: SQL keyword and identifier case (`sql-case`), codec name case (`codec-name`),
the `typing.cast` type argument (`cast-type`) and pattern case under `re.IGNORECASE`
(`ignorecase-pattern`). It accepts a survivor only when the original and the mutant
differ in exactly one place and that place satisfies the rule, lists each accepted
mutant with its rule, and fails on every other survivor, including those recorded
here with a proof by hand. `tests/test_mutation_equivalence.py` pins what each rule
must accept and what it must refuse.

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

The same holds for subprocess output read as text: `run_git`, the control plane's
`discovery.git` and `execute_verifier` pass `encoding="utf-8"`, and a mutant that
drops it or sets it to `None` decodes with the same UTF-8 locale on Linux. On
Windows the locale default is a legacy code page, and `tests/test_output_encoding.py`
and `test_git_listing_keeps_non_ascii_paths` fail on the mutated call there.

## Equivalent by the language: four families

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

**`check=False` in `subprocess.run`.** `False` is the default, and the argument is
only tested for truth, so setting it to `None` or dropping it cannot make the call
raise. Checked: `subprocess.run(["false"], check=None)` and `check=False` both
return exit status 1 without raising. Where the argument was only restating the
default, it was removed instead (`discovery.git`, the audit's repository check).

## `integrity._file_changes` — the previous-line sentinel

```python
previous = ""
...
elif line == "+++ /dev/null" and previous.startswith("--- a/"):
```

`previous` is only read to see whether it starts with `--- a/`, and it holds the
starting value only while the first line is examined. Any starting string that does
not start with `--- a/` therefore gives the same pairing, including the mutant's
`"XXXX"`. Checked by executing `_file_changes` with the starting value replaced by
`"XXXX"`, `"x"`, `"--- b/"` and `""` on a diff whose first line is `+++ /dev/null`, a
deleted-file diff and an empty diff: every variant returned identical pairs. `None`
is not in this family: it raises on that first line, and a test kills it.

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

## `Store.get` type guards: which are equivalent, and which only a corrupt store reaches

`Store.get(identifier, kind)` refuses a record of another kind. Where the caller
supplies the identifier, that refusal is behaviour, and those guards are killed
by `tests/control/test_record_kinds.py`: task entry points, `transition`, both
ends of `Knowledge.link`, a claim's subject and evidence, the identity a
changeset updates, and the changeset a rollback names.

The remaining guards fall into three groups, told apart by where the identifier
comes from.

**Equivalent: the same identifier was already read with the same kind earlier in
the call.** The second guard cannot fail when the first passed.
`create_workspace` and `refresh_workspace` re-read the task inside the transaction
that updates it; `verify` re-reads it in its `finally` after `owned` read it as a
task; `Plane._expire` reads a lease's task twice; `Knowledge.claim` reads its
subject a second time before writing.

The last one needed care, and the order matters. It is the *second* read that is
redundant, not the first: a declared claim with a subject of the wrong kind is
refused identically by either read, so dropping the kind at the first read goes
unseen on that path. The first read is observable only when evidence is checked
between the two, which is the path the test takes.

**Equivalent: the identifier is the record's own id, taken from a listing of that
kind.** `verify` re-reads its lease by the id of a record that `owned` found
through `store.list("lease")`, which only returns leases.

**Not equivalent, and declared rather than killed: an identifier stored inside
another record.** `task["workspace_id"]` (`cleanup`, `integration_gate`,
`merge_workspace`, `refresh_workspace`, `workspace_root`), a lease's `task_id` and
`agent_id` (`_expire`, `claim`, `heartbeat`), a task's `requirements` and
`dependencies` (`binding`, `proof_current`, `context`, `readiness`), a claim's
`subject` and `evidence_refs` and an evidence record's `task_id` (`invalidate`,
`resolve_claim`, `claim`), and a changeset's entities and the `edges` table
(`rollback_changeset`, `apply`).

Each of these identifiers is validated when the record holding it is written, so
the guard only acts on a store edited outside the plane. They are reachable — by
forging a record into a state the plane never writes — and one of them is killed
that way (`proof_current` reading proof of another kind), because a proof list is
the input that decides whether work counts as done. The rest are left as
survivors: what the plane does with a corrupt store is defence in depth, not a
contract a caller relies on, and pinning it guard by guard would fix behaviour
nobody has specified. They are the candidates for a later cycle, not equivalents.

## Examined one by one: equivalents found while killing survivors

Three batches of tests (#20, #21, #22) examined about 380 survivors individually:
each mutant was applied to the source and only the tests of its module were run,
after a run of the same tests without the mutant. About half were behaviour
without a test and are killed. The families below are the rest; every claim that
depends on the language or a library was executed, not argued.

**`sqlite3.Row` and HTTP header lookups ignore case.** `row["KIND"]` reads the
same column as `row["kind"]`, and `self.headers.get("host")` the same header as
`"Host"`. Checked: `row["ID"] == row["id"]` and `row["PAYLOAD"] == row["payload"]`
on a real row, and `get("host") == get("HOST") == get("Host")` on an
`http.client.HTTPMessage`. Sites: `Store.get`, `Store.list`, `Store.entities_at`,
`Store.history`, `Store.timeline`, `Knowledge.impact`'s edge columns, and the
console's `Host` check.

**Values that behave the same in every place they are used.**
- `None` for `False` where the value is only tested for truth: `check`, `nested`,
  `Session.initialized` and `ready`, `getattr(..., None)`, `passed` in `verify`,
  `json.dumps(allow_nan=None)` (checked: it refuses `nan` exactly as `False`).
- `"SHA256"` for `"sha256"` in `hashlib.file_digest` (checked: same digest).
- `split("?")` and `split("?", 2)` for `split("?", 1)` when only element 0 is read
  (checked on a path with two `?`); `rsplit` is not in this family and is killed.
- A token or staging name of another random length (`token_urlsafe`, `token_hex`).
- A comparison's starting value that every real timestamp exceeds (`context`'s
  latest evidence).

**Initial values always overwritten before they are read.** `execute_verifier`
sets `status` to `UNKNOWN` and `duration_seconds` to `0.0`, then every path that
returns the result replaces both. `adopt` records `coverage` and then calls
`_index`, which rewrites it from the same report.

**Checks repeated by the code that follows.** `approve_command` and `checkpoint`
call `safe_data`, and `store.put` calls it again on the same data. `proof_current`
checks that each requirement is active and not stale, but the evidence binding
records each requirement's version and `readiness` refuses to verify a task whose
requirement is inactive or stale, so any later change already fails the binding.
Its `visited` set only matters for a dependency cycle, and a task's dependencies
must exist when it is created and cannot change afterwards. A second read of a
claim's subject repeats the first.

**Loop exits that cannot skip work.** `Knowledge.impact` walks a FIFO queue, so once
an entry at the depth limit is dequeued every later entry is at that depth too:
`break` there equals `continue`. `serve` reads the rest of an oversized line in
chunks, and the chunk size does not change what is refused.

**Directories whose grandparent always exists.** Every `mkdir(parents=True)` that
survives creates a directory directly under the project root or under `.agentic/`,
which `init` or `adopt` created before: `_copy_item`, `_install_payload`,
`_write_json`, `adopt`, `migrate_payload` and both writes in `execute_verifier`.

**Defaults no input reaches.** The key is required by the schema that validates
the document first (`project` in a quality configuration, a verifier's
`working_directory` and `expected_exit_code`), or the plane always writes it
(`conflicts` on a claim, `occurrence` on a symbol). A default that an input can
omit is not in this family: nine such sites (eighteen mutants) are killed by documents that leave
the key out.

**Others.** `doctor` collects missing tools only to test the list for emptiness;
the tools themselves are reported in `tools`. A requirement graph whose `edges` is
an object is iterated by key and every key is skipped, so the early return adds
nothing. `_prepare_target`'s `dry_run` and `resume`'s `budget` defaults are never
used by a caller.

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
