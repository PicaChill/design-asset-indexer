# Headless GUI workflow architecture

This document describes the Python application core that a future desktop GUI may call. It does not describe an implemented GUI and adds no GUI dependency.

## State model

The presentation layer must enforce this sequence:

```text
SETUP
  -> INSPECTING
  -> INSPECTED
  -> DRY_RUNNING
  -> DRY_RUN_REVIEW
  -> USER_CONFIRMED
  -> EXECUTING
  -> RESULT
```

Formal execution accepts a `SignatureExecutionPlan`, not a second set of replacement parameters. Any edit to input, output, exact source text, replacement text, optional exact layer name, recursive mode, include glob, or maximum file count requires a new plan.

## Public headless API

The workflow is split between:

- `workflow_models.py`: immutable parameters, snapshots, plan items, validation results, events, cancellation, and typed run results;
- `workflow.py`: inspect orchestration, plan creation, validation, formal execution, and privacy-safe diagnostics;
- `signatures.py`: the single implementation of candidate selection, exact matching, copied-output mutation, fail-clean, and v0.2 report writing.

The main entry points are:

```python
inspect_signature_workflow(options, adapter, ...)
create_signature_execution_plan(options, rule, adapter, ...)
validate_execution_plan(plan)
execute_signature_plan(plan, adapter, ...)
build_public_diagnostic(result)
```

`execute_signature_plan` deliberately has no `old_text`, `new_text`, `layer_name`, input, or output parameter. Those values come only from the immutable plan.

## Execution plan

A plan records:

- immutable `WorkflowOptions` and one immutable `SignatureRule`;
- every candidate relative path in deterministic order;
- the selected PSD relative path, size, and `mtime_ns`;
- selected-output existence, symlink, size, and `mtime_ns` state;
- v0.2-compatible decisions and error codes;
- `max_files_reached`;
- a deterministic SHA-256 `plan_id` over canonical JSON.

The fingerprint contains replacement text because text changes must change the plan. The fingerprint is not a diagnostic payload, and normal events/public diagnostics do not expose that text.

Full PSD SHA-256 is intentionally not part of routine plan creation. Stale detection uses relative path, size, and `mtime_ns`, plus the full candidate path list and output state.

## Stale validation

Validation can return:

```text
VALID
STALE_PARAMETERS
STALE_SOURCE_SET
STALE_SOURCE_FILE
STALE_OUTPUT
```

Before the first formal PSD mutation, validation checks the plan fingerprint, full candidate path set/order, selected source stats, truncation state, and selected output states. A stale plan blocks the entire formal run before any PSD output is created.

After execution starts, each item is checked again at its file boundary. If a later source or output becomes stale:

- no later file starts;
- completed earlier outputs are retained;
- the result is marked `stale=True`;
- `cancelled=False`;
- workflow status is `EXECUTION_STOPPED_PLAN_STALE`;
- the run is not reported as complete.

## Cooperative cancellation

`CancellationToken` uses `threading.Event` and is checked only between files.

- Cancellation before the first file creates no PSD output.
- Cancellation requested after `FILE_STARTED` does not interrupt the active file.
- The active file completes or fails normally, and no next file starts.
- Cancellation requested during the last file does not relabel an otherwise complete run.
- The workflow does not kill Photoshop, a worker thread, or a subprocess.

A future Windows GUI must create and use its Photoshop COM adapter in the same worker thread. COM objects must not be passed between the GUI thread and worker thread.

## Structured events

The optional event sink receives deterministic events:

```text
RUN_STARTED
FILE_STARTED
FILE_RESULT
RUN_COMPLETED
RUN_CANCELLED
RUN_STOPPED_STALE
```

Events contain a phase, event kind, index, total, optional relative path, and optional status/decision. They do not contain absolute paths or replacement text. The sink is observational only and cannot make matching decisions.

Event callback exceptions are isolated as `EVENT_SINK_ERROR`. They do not change matching, copied-output protection, fail-clean, or the current file's business result.

## In-memory results and reports

Inspect and execution return frozen typed results containing:

- items;
- an immutable summary view;
- processed and remaining counts;
- `cancelled` and `stale`;
- `max_files_reached`;
- safe workflow diagnostics.

The existing CSV, JSONL, and `summary.json` reports are still written. Workflow-only metadata such as `plan_id`, `cancelled`, `stale`, and `remaining_count` is not added to the v0.2 persisted summary schema.

## Privacy-safe diagnostics

`build_public_diagnostic` includes only version, phase, counts, status counts, truncation, cancellation/stale flags, error codes, and safe diagnostic codes.

It excludes by default:

- absolute and relative paths;
- real filenames;
- old, new, or current text;
- layer names;
- raw Photoshop document content.

Detailed rows and reports remain local and may contain private names/text, so they must be reviewed before sharing.

## Preserved v0.2 behavior

The workflow uses the same helpers as the CLI for:

- exact `current_text == old_text` matching;
- optional exact layer-name filtering;
- zero/ambiguous match skips;
- explicit recursive/include/max-files selection;
- input/output non-overlap;
- existing-output protection;
- copy-before-replace;
- fail-clean of only newly created failed outputs;
- v0.2 report decisions and statuses.

`SKIPPED_NO_MATCH` still does not copy an unchanged PSD. There is no multi-rule engine, copy-unmatched option, font/glyph detection, or role inference in this phase.
