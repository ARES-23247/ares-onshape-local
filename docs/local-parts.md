# Local development and native construction

The shared definition is a small JSON recipe with millimetre dimensions, a label, owning design and datum.
Onshape has no supported offline native-document upload format. STEP/Parasolid imports preserve geometry
but do not transfer the original feature tree. This workflow creates native features online from the
definition instead. It makes no outbound Onshape requests and uses no FeatureScript evaluation.

| Family | Native construction | Current evidence |
| --- | --- | --- |
| spacer | Constrained annulus and extrusion | Historical live default/changed pilot |
| mounting_bracket | Constrained base/upright/hole sketches and extrusions | Historical live default/changed pilot |
| hole_pattern_plate | Constrained rectangular and four-hole sketches and extrusions | Historical live default/changed pilot |
| flanged_hub | Radial section, separate axis sketch and full revolve | Local geometry and simulated request checks |
| radial_hole_plate | Annulus, seed hole cut, separate axis and six-instance face pattern | Local geometry and simulated request checks |
| lofted_guide | Offset outlet plane, ordered outer loft and inner cut loft | Local geometry and simulated request checks |

1. Call save_part_definition with the family and dimensions. Select the owning configured design, or
   shared for an independent sandbox. It saves a content-addressed private definition and returns its path.
2. Call preview_part_definition with definition_source. It creates a FEASIBILITY bundle with a browser
   preview, checked STEP roundtrip, experimental STL, source definition and construction instructions.
3. Save a fresh complete empty-target Part Studio feature-list receipt through session-authenticated
   Explorer. Call prepare_part_definition with definition_source, head_receipt and the preview's record
   as preview_record. Native target ownership and the pinned schema revision must match.
4. Call prepare_recipe_step. Reobserve the live head immediately before submitting its standard feature
   body through Explorer. Save a fresh actual feature list and call bind_recipe_step. Repeat until complete.
   part_development_status returns progress and the next action. Pending requests require readback and
   binding; never resubmit blindly after a timeout. The local journal does not lock the Onshape document.
5. Call verify_native_recipe using fresh feature states and actual bodydetails/massproperties receipts at
   the same immutable microversion. It checks the analytic surfaces, hole axes/positions, bounds, areas
   and volume. An attached preview bundle must still match its source and artifact hashes.
6. Save a second definition with a meaningful dimension change. Call prepare_part_definition with the
   existing manifest_source and fresh head_receipt (plus a new preview_record when preview comparison is
   needed). Submit the bulk variable update, bind and verify actual changed geometry. Then call
   verify_part_parameter_change with manifest_source and the baseline geometry report. Restore selected
   dimensions through another explicit definition revision when appropriate.

Each native feature depends on actual returned IDs. Requests are generated one step at a time, not as
one precompiled upload file. Definitions do not include arbitrary code, keys, browser credentials or
project source identities. Runtime journals/receipts stay in the private configured workspace.
Live checks for the added families are still required; local tests cannot establish Onshape regeneration.

The isolated geometry environment is optional. Set ARES_ONSHAPE_CAD_PYTHON to its interpreter when it is
outside the repository. Existing build_part_recipe and older unbound native recipe journals still work.
For a client whose MCP tools have not reloaded, src/part_development_cli.py exposes the five shared
definition operations using --input with a private workspace JSON object of tool arguments:

```text
python src/part_development_cli.py save_part_definition --input part-arguments.json
```

Use CLI/environment paths appropriate to your installation. Browser capability and an editable Onshape
session are still supplied by the host/operator; neither the CLI nor MCP executes native requests.

Official references: [import limitations](https://cad.onshape.com/help/Content/Document/importing_files.htm),
[feature APIs](https://onshape-public.github.io/docs/api-adv/featureaccess/),
[annual accounting](https://onshape-public.github.io/docs/auth/limits/).
