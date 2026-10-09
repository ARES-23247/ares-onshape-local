# Tools and receipts

The stdio server exposes twenty-five tools. All execution against Onshape belongs to the host browser.

| Tools | Scope |
| --- | --- |
| `workflow_status`, `design_context` | Local setup, source identities, plan hashes and refresh queue |
| `search_snapshots`, `lookup_snapshot`, `read_snapshot` | Hash-checked search, immutable identities and bounded JSON-pointer reads |
| `register_snapshot` | Index an operator-confirmed completed session GET |
| `prepare_native_change` | Standard Part Studio feature create/update JSON with a head precondition |
| `review_native_result` | Saved feature states at the expected microversion |
| `mechanism_calculation` | Roller speed, RPM and shaft-stack arithmetic |
| `sync_notifications` | Ingest saved local events and queue registered documents for refresh |
| `list_part_recipes`, `build_part_recipe` | Three bounded optional FEASIBILITY recipes |
| `prepare_native_recipe`, `prepare_recipe_step` | Target-bound journal and one standard feature body |
| `bind_recipe_step`, `prepare_recipe_update` | Bind actual IDs; update existing named variables |
| `native_recipe_status`, `verify_native_recipe` | Journal and saved immutable BRep/volume verification |

Resources: `ares://onshape/workflow`, `ares://onshape/recipes`,
`ares://onshape/native-recipe-profile`, `ares://onshape/designs/{design}/plan`.

Additional tools in version 0.2:

| Tools | Scope |
| --- | --- |
| register_reference_snapshot | Read-only configured purchased/shared-source receipt indexing |
| prepare_assembly_change | Complete healthy mate/group/connector/relation templates with head preconditions |
| review_assembly_result, review_assembly_motion | Saved states, exact root-part references, sampled poses and neutral restoration |
| native_change_status, record_native_submission, reconcile_native_change | Target-scoped generic request journal and actual result binding |

Save actual completed reads inside your workspace:

```json
{
  "requestUrl": "<actual executed official API GET URL>",
  "method": "GET",
  "httpStatus": 200,
  "transport": "onshape-session",
  "observedAt": "<actual timezone-aware ISO timestamp>",
  "units": "m",
  "response": {}
}
```

Replace the empty response with completed JSON. Never include cookies, authentication headers,
XSRF tokens, keys or secrets. Transport/timestamps are operator assertions, not cryptographic proof.

Preparation requires a successful workspace Part Studio feature-list receipt observed within 30 minutes,
matching the selected design, workspace and element. It writes `.ares-onshape/` files containing
`sourceMicroversion` and `rejectMicroversionSkew=true`. Reobserve the head immediately before submission;
receipt age does not prove freshness. Updates require an existing feature ID and preserved parameters.

The feature list must be complete, unskewed and unfiltered at the end of the default configuration.
Part Studio preparation includes cPlane, circularPattern, linearPattern and loft alongside the original
types. Assembly preparation requires a healthy template of the same native variant from that head.
Use the current Explorer API version and standard parameter/query serialization.

Generic preparation returns a manifest path. Record submitted before browser Execute, then reconcile
against a fresh actual feature list. A pending request blocks further preparation for that target across
processes. Missing results, unchanged parameters and duplicate candidates do not complete it. Only an
unsubmitted request can be cancelled without result evidence. A matching saved session POST 4xx
rejection can release it; 408/server failures stay uncertain. For 429, save the actual Retry-After duration
in seconds as retryAfter. The target remains blocked until that deadline. Target locks are local coordination,
not a lock on Onshape; reobserve its head and preserve other agents' changes.

Shared references in private configuration identify the allowed document and optional workspace/element_ids.
register_reference_snapshot indexes their actual reads under shared without granting edit ownership.
Read configurations/filters/units still form exact cache identities. Edits retain their owning design guard.

review_assembly_result requires feature and definition receipts at the same expected microversion.
expected_part_references names root instances with instance_id and a reference containing documentId,
elementId, partId, configuration and documentVersion or documentMicroversion. Optional expected_poses
names occurrence paths and 16-value row-major transforms with translations in metres. Check the owning
subassembly separately for a nested replacement. Suppressed recovery features must be explicitly named.

review_assembly_motion takes baseline/restored definition receipts and observations with source,
microversion, command (feature_id, value, units) and expected_poses. It checks scoped saved matrices and
all baseline occurrences at restoration; it does not execute commands or prove continuous interference
clearance. Inspect live regeneration/motion and physical behavior separately.

Cache identities include API version/path, configuration, duplicate query parameters, filters and units.
Changed files fail hash checks; missing/conflicting records are misses. Workspace snapshots remain
historical context. Exact cache reuse is limited to immutable version/microversion geometry.

Use `src/onshape_context.py` for indexing, search, lookup, event ingestion and explicit
`refreshed <document-id> <observed-microversion> --confirmed-session-read` records. Save/index refreshed
receipts before clearing a dirty flag. The usage ledger is manual, not Onshape's annual counter.
