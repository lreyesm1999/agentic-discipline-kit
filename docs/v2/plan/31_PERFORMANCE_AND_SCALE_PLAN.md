# Performance and Scale Plan

## MVP performance targets

Local repository:
- status query < 300 ms on warm cache;
- task claim < 200 ms;
- checkpoint write < 300 ms;
- knowledge query < 500 ms for common indexed traversal;
- adoption progress streaming;
- graph updates incremental, not full rebuild by default.

## Large repository strategy

- incremental indexing;
- file hash cache;
- language-adapter boundaries;
- symbol-level graph updates;
- lazy doc ingestion;
- FTS;
- query limits;
- bounded context assembly.

## Avoid premature distributed design

Only consider server/distributed mode after measuring:
- concurrent agents > local SQLite comfort;
- team-shared state;
- remote workers;
- significant lock contention;
- large knowledge query workloads.
