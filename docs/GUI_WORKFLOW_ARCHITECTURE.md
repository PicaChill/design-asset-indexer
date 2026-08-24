# GUI workflow architecture

The public desktop entry point uses the novice-first `PremiumSimpleWindow`.
The earlier five-step `MainWindow` remains in the source tree as an internal
regression reference, but it is no longer the public presentation. Both
presentations depend on the same controller, workers, and immutable headless
workflow; the Premium Simple window does not duplicate matching, copy, or
fail-clean behavior.

```text
PremiumSimpleWindow (public presentation)
  -> WorkflowController (single GUI state authority)
  -> RunningJob / WorkflowWorker (thread and COM boundary)
  -> workflow.py / workflow_models.py (immutable plan and typed results)
  -> signatures.py / PhotoshopAdapter (existing business behavior)
```

The public presentation hides advanced settings, detailed rows, and diagnostics
by default. Its compact confirmation dialog still binds the exact reviewed plan
object, plan ID, and controller generation before frozen-plan execution.

## State model

The presentation layer must enforce this sequence:

```text
SETUP
  -> INSPECTING
  -> INSPECTED
  -> PLANNING
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
plan_signature_workflow(options, rule, adapter, ...)
create_signature_execution_plan(options, rule, adapter, ...)
validate_execution_plan(plan)
execute_signature_plan(plan, adapter, ...)
build_public_diagnostic(result)
```

`execute_signature_plan` deliberately has no `old_text`, `new_text`, `layer_name`, input, or output parameter. Those values come only from the immutable plan.

`plan_signature_workflow` is the cancellable GUI/controller entry point. It
returns a frozen `PlanRunResult`; a cancelled or stale run has `plan=None` and
therefore cannot be executed. `create_signature_execution_plan` is a
convenience wrapper over the same planning engine and requires planning to
finish completely.

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

Preflight validates every planned output path, including paths belonging to
later items. Existing ancestor components must be directories, and resolved
containment catches Windows junction/reparse-point and symlink escapes. A bad
ancestor is `STALE_OUTPUT` and blocks all formal mutation.

After execution starts, each item is checked at its file boundary and again
after `FILE_STARTED`, immediately before mutation. This post-callback check
prevents caller code or another process from changing a source/output path in
the event-to-mutation gap. Path/filesystem errors returned by the mutation
helper are revalidated: a changed boundary stops stale, while a genuine
Photoshop/file failure with still-valid boundaries remains an ordinary
per-file failure. If a later source or output becomes stale:

- no later file starts;
- completed earlier outputs are retained;
- the result is marked `stale=True`;
- `cancelled=False`;
- workflow status is `EXECUTION_STOPPED_PLAN_STALE`;
- the run is not reported as complete.

## Cooperative cancellation

`CancellationToken` uses `threading.Event` and is checked only between files
for inspect, dry-run planning, and formal execution.

- Cancellation before the first file creates no PSD output.
- Cancellation requested after `FILE_STARTED` does not interrupt the active file.
- The active file completes or fails normally, and no next file starts.
- Cancellation requested during the last file does not relabel an otherwise complete run.
- A cancelled or stale dry-run emits a terminal `RUN_CANCELLED` or
  `RUN_STOPPED_STALE` event and never returns an executable plan.
- The workflow does not kill Photoshop, a worker thread, or a subprocess.

### Photoshop COM worker lifecycle

The Windows GUI keeps the complete COM apartment and adapter lifecycle
inside one worker thread:

```text
pythoncom.CoInitialize()
create/connect/use PhotoshopAdapter
run all workflow calls for that adapter
discard adapter
pythoncom.CoUninitialize()
```

- The GUI thread must not call `PhotoshopAdapter.is_available()` or `.version`,
  because either may establish the cached COM connection.
- A connected adapter and every COM object it owns must never cross threads.
- Do not create one temporary thread per button while reusing one adapter.
- The current worker creates a fresh adapter for a phase. `CoInitialize`,
  adapter creation and use, and `CoUninitialize` stay in that same worker
  thread.

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

Results distinguish two completion levels:

- `planned_items_complete`: every selected/planned item finished without
  cancellation or stale state;
- `corpus_complete`: planned items finished and no candidates were left outside
  the max-files selection.

The fail-safe `complete` alias means `corpus_complete`. A finished 100-file run
with `max_files_reached=True` therefore cannot be reported as fully complete.
Typed plans/results also expose `candidate_count`, `selected_count`,
`unplanned_count`, and `partial_plan` without exposing filenames.

The existing CSV, JSONL, and `summary.json` reports are still written. Workflow-only metadata such as `plan_id`, `cancelled`, `stale`, and `remaining_count` is not added to the v0.2 persisted summary schema.

### Completion authority for the GUI

The frozen typed result is the only authority for GUI completion state.
`summary.json` remains a v0.2-compatible business summary and cannot tell a GUI
whether a workflow was cancelled, stopped stale, or ended as a partial run. A
GUI must not infer “complete” from the sum of `status_counts`, and must not use
`summary.json` alone for progress/completion decisions. If crash recovery later
needs persisted workflow state, it requires a separately designed metadata
artifact; this phase does not add ad-hoc fields to the v0.2 summary.

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
