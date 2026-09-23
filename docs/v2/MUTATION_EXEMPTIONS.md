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
differ in exactly one place and that place satisfies the rule, and lists each accepted
mutant with its rule. `tests/test_mutation_equivalence.py` pins what each rule must
accept and what it must refuse.

The equivalents proven by hand below are accepted through
`policies/mutation-exceptions.json`, the reviewed exception list. Each exception names
the function, the exact line the mutant changes before and after, its family and the
reason, which points back to a section of this file. The file is a protected path,
so any change to it shows in the protected check and needs review. The gate accepts
a survivor only when an exception matches its changed line exactly. It fails on every
other survivor, and on any exception that no longer matches one.

## How a survivor leaves the list

Five batches of tests (#20, #21, #22, #24, #25) examined the survivors one by one. Each
mutant was applied to the source and the tests of its module were run, after a run
of the same tests without the mutant. A survivor was resolved in one of three ways,
in this order of preference:

1. **A test**, when the mutant exposed behaviour nothing checked.
2. **Removing the code**, when the mutant changed something no input can reach: a
   default for a key the schema requires, an initial value every path overwrites, or
   a second mechanism doing the work of the first. The mutant disappears with the
   dead code, and no test is written against code that has no effect.
3. **An entry here**, only when neither applies.

A check that repeats an earlier one is kept as defence in depth and tested by
bypassing the check in front of it. `create_task`'s server-owned field guard runs
with contract validation replaced. The secret checks in `approve_command` and
`checkpoint` run with the store's own check replaced. `proof_current`'s requirement
and cycle checks run with `fresh` replaced. `verify`'s busy guard is reached with
changes outside the scope, which the next check would otherwise report. `complete`'s
comparison of the post-merge binding is reached with a forged merge record, since
`merge_workspace` itself refuses to record a merge the primary does not match.

## Equivalent by the language: four families

Each rule below is a property of Python itself, checked by running it, so it holds
for every site of that shape rather than needing an argument per mutant.

**`typing.cast` type argument.** `cast(T, value)` returns `value` unchanged at
runtime and never inspects `T`. Mutating the type argument, including to `None`,
cannot change what the call returns. Checked: `cast(None, value) is value` and
`cast(list[int], value) is value` are both true.

**Codec name case.** `"utf-8"`, `"UTF-8"` and `"Utf-8"` resolve to the same codec
through `codecs.lookup`, so flipping the case of an explicit encoding name cannot
change a single byte read or written (the console's response body, the ledger's
record hash).

**Pattern case under `re.IGNORECASE`.** When a pattern is matched with
`re.IGNORECASE`, changing the case of its literal characters cannot change what it
matches or what its groups capture. A mutant that *removes* the flag is not in this
family; it changes behaviour and stays on the kill list. Where the text was already
lowercased before matching (`risk`), the flag was the duplicate and was removed.

**`check=False` in `subprocess.run`.** `False` is the default, and the argument is
only tested for truth, so setting it to `None` or dropping it cannot make the call
raise. Checked: `subprocess.run(["false"], check=None)` and `check=False` both
return exit status 1 without raising.

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
the statement is unchanged.

## Lookups that ignore case: `sqlite3.Row` and HTTP headers

`row["KIND"]` reads the same column as `row["kind"]`, and `self.headers.get("host")`
the same header as `"Host"`. Checked: `row["ID"] == row["id"]` and
`row["PAYLOAD"] == row["payload"]` on a real row, and
`get("host") == get("HOST") == get("Host")` on an `http.client.HTTPMessage`. Sites:
`Store.get`, `Store.list`, `Store.entities_at`, `Store.history`, `Store.timeline` and
the console's `Host` check. `Knowledge.impact` now unpacks `source, target` by
position and no longer has such a lookup.

## Encoding: killed where it matters, equivalent where the text is ASCII

Dropping `encoding="utf-8"` falls back to the platform's preferred encoding. That is
UTF-8 on Linux, where the mutation run happens, and a legacy code page on Windows.
`tests/legacy_code_page.py` makes a missing encoding mean cp1252 on every platform,
and `tests/test_utf8_on_legacy_code_pages.py` round-trips accented text through
each reader, writer and subprocess. Those mutants are killed.

What remains is text that is ASCII by construction. `json.dumps` escapes every
non-ASCII character unless told otherwise, so encoding its output with another codec,
or with none, produces the same bytes. Checked:
`json.dumps({"a": "café"}).encode("utf-8") == json.dumps({"a": "café"}).encode("ascii")`.
About two dozen survivors encode or write `json.dumps` output this way.

## `Store.get` type guards: rereads and guards another guard pre-empts

`Store.get(identifier, kind)` refuses a record of another kind. Where the caller
supplies the identifier, `tests/control/test_record_kinds.py` kills the guard. Where
the identifier is stored inside another record — a task's workspace, requirements
and dependencies, a lease's task, a claim's subject and evidence, an evidence
record's task, a changeset's entities, the edges table — `tests/control/
test_corrupt_references.py` forges that reference to a record of the wrong kind and
pins the `NOT_FOUND` refusal.

The survivors left are equivalent for one of two reasons:

- **The same identifier was already read with the same kind earlier in the call.**
  `create_workspace` and `refresh_workspace` re-read the task inside the transaction
  that updates it. `verify` re-reads it in its `finally` after `owned` read it.
  `Plane._expire` reads a lease's task twice. `Knowledge.claim` reads its subject a
  second time before writing.
- **An earlier guard on the same path already refuses.** `binding` reads a task's
  requirements before `proof_current` does, and `workspace_root` reads the workspace
  before `merge_workspace` and `refresh_workspace` do. `heartbeat` reads its lease's
  agent after `owned` has already authenticated that agent. `verify` re-reads its
  lease by the id of a record that `owned` found through `store.list("lease")`.

## Directories whose grandparent always exists

Every `mkdir(parents=True)` that survives creates a directory directly under the
project root or under `.agentic/`, which `init` or `adopt` created before: `adopt`,
`migrate_payload` and both writes in `execute_verifier`. `tests/test_install_helpers.py`
kills the sites where the parent can be missing.

## Others, each checked

- **`None` for `False`, including a missing `dict.get` default, where the value is only tested for truth or passed through `bool`.**
  `assurance` migrates unless `dry_run` is true, so `args.get("dry_run", False)`,
  `args.get("dry_run", None)` and `args.get("dry_run")` all migrate. `normalized`
  stores `bool` of a missing `supports_incremental`, and `bool(None)` is `False`.
  Checked: both migrate calls write the upgrade, and both normalizations store `False`.
- **Undeclared evidence is already measured.** Migration classifies an undeclared
  kind as `MEASURED`. That descriptor's own class is `MEASURED`, and every declared
  descriptor is stored with `declared` true, so a condition forced true records the
  same class. Checked on legacy evidence of a kind nobody registered: both versions
  store `MEASURED`.
- **`None` for `False` or `""` where the value is only tested for truth.**
  `getattr(args, "check_tools", None)` and `"check_paths"`, the adapters' `nested`,
  the flags `pending_id`, `required_tool_missing`, `has_required`, `reaches_evidence`,
  `passed`, `Session.initialized` and `ready`, `check=None` or a dropped `check` in
  `subprocess.run`, and `json.dumps(allow_nan=None)` (checked: it refuses `nan` exactly
  as `False` does).
- **`"SHA256"` for `"sha256"`** in `hashlib.file_digest` (checked: same digest).
- **A slice one past the end.** `relative.parts[:len(parts) + 1]` equals
  `relative.parts[:len(parts)]`, so `range(1, len(parts) + 2)` checks the same
  prefixes as `range(1, len(parts) + 1)` (`files`, `validate_inputs`).
- **Random lengths.** `secrets.token_urlsafe(None)` uses the default entropy of 32
  bytes, the value the code passes (checked: both give 43 characters). `adopt`'s
  staging directory name may be any length; it is found by prefix and renamed.
- **`git rev-parse --VERIFY REBASE_HEAD`.** `rev-parse` echoes an option it does not
  know and still resolves the revision, exiting 0 when `REBASE_HEAD` exists and
  failing when it does not, exactly like `--verify` (checked in a repository with and
  without a rebase in progress).
- **Placeholders.** `Knowledge.claim` validates a claim through `entity_contract`
  with a fixed `type` of `"claim"`, where any non-empty text passes. It stores
  nothing. `execute_verifier` starts `duration_seconds` at `0.0` so the key keeps
  its place in the written result, and every path that returns overwrites it.
- **`integrity._file_changes` — the previous-line sentinel.** `previous` is only
  read to see whether it starts with `--- a/`. It holds the starting value only while
  the first line is examined, so any starting string that does not start with
  `--- a/` gives the same pairing, including the mutant's `"XXXX"`. Checked on a
  diff whose first line is `+++ /dev/null`, a deleted-file diff and an empty diff.

## Resolved rather than excepted

Three survivors once listed here as known but unproven were settled in #25 instead of
being excepted. A run with no recorded deadline is tested half a second after the
epoch. The latest evidence is now chosen by a stable sort, which leaves no comparison
to mutate. The post-merge binding check is tested past a forged merge record.

## Method

Apply the mutation to the source, clear `__pycache__` and run with `-B`
(`PYTHONDONTWRITEBYTECODE=1`), then run the tests that cover the line, after a
baseline run of the same tests without the mutant. Every mutation used here is
length preserving, so a cached `.pyc` written in the same second will silently run
the unmutated code and report a false survivor.

Three techniques reach behaviour a plain run cannot:

- A **legacy code page** (`tests/legacy_code_page.py`) for encodings.
- A **frozen clock** (`time.time` replaced by a fixed instant) for boundaries: a lease
  expiring at exactly the current instant, and a lease that ends as a verifier
  finishes.
- A **forged store** for references another record holds: a reference written
  directly with `store.put`, or an edge inserted into the table, pointing at a
  record of the wrong kind.
