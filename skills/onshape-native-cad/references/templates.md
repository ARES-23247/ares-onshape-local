# Native request examples

The JSON files under examples/ are sanitized standard-feature patterns, not a tested complete generator
or a transport client. They contain no credentials or live document target. Resolve current schemas and
native queries in the intended Part Studio before execution.

- variable-length.json: named plateThickness length variable.
- sketch-circle.json: closed two-arc circle on the default Top plane.
- extrude-new.json: new solid from that sketch region driven by #plateThickness.
- verification-provenance.json: limitations of the adapted patterns.

Read default planes and native feature specifications first. The example plane query is not universal.
Create the variable/sketch, capture the actual sketch feature ID and replace SKETCH_FEATURE_ID in the
extrude. Resolve the intended sketch region. Onshape-generated query serialization is permitted;
it is distinct from evaluating a custom FeatureScript geometry program.

The example sketch contains numerical geometry; add meaningful native dimensions/constraints.
Check fresh feature states, actual geometry and the intended edit after changing the variable.
Use session-authenticated browser/Explorer submission. Historical pattern evidence does not establish
verification in a new target.
