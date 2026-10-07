# Tools and receipts

The stdio server exposes eighteen tools. All execution against Onshape belongs to the host browser.

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

Cache identities include API version/path, configuration, duplicate query parameters, filters and units.
Changed files fail hash checks; missing/conflicting records are misses. Workspace snapshots remain
historical context. Exact cache reuse is limited to immutable version/microversion geometry.

Use `src/onshape_context.py` for indexing, search, lookup, event ingestion and explicit
`refreshed <document-id> <observed-microversion> --confirmed-session-read` records. Save/index refreshed
receipts before clearing a dirty flag. The usage ledger is manual, not Onshape's annual counter.
