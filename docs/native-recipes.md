# Native recipe bridge

The spacer, mounting bracket and hole-pattern plate families produce optional local previews and ordinary
native Onshape variables, dimensioned sketches and extrusions. This is a recipe compiler, not recovery of
STEP history or translation of arbitrary build123d programs.

The inherited profile uses API v17, native library 3083 and the target's serialization version. Another
library/API revision fails closed; validate and update the profile deliberately when Onshape changes.
Historical geometry is represented by anonymized fixtures in `tests/fixtures`. Public tests do not create
native geometry or establish compatibility with your current Onshape revision.

Observe an empty target Part Studio through session-authenticated Explorer. Registered documents require
their owning design; `shared` selects a separate sandbox. Populated recipe targets are rejected to preserve
existing models. General edits belong in `prepare_native_change`.

Prepare one feature, reobserve the head, submit through Explorer, save a complete fresh readback and bind
the actual returned IDs. A pending create blocks another create. After a timeout, read the target before
retrying. Hashes, intent fingerprints and an exclusive journal lock detect modified requests, unexpected
external edits and concurrent writers. Updates change existing named variables while retaining IDs.

Read `bodydetails` and `massproperties` at the exact observed head microversion. The verifier checks one
solid, expected planar/cylindrical surfaces, hole axes/positions, bounds, areas, orientation and SI volume.
Healthy states and geometry comparisons do not certify loads, assembly motion, printed fit or fabrication.
Verify actual geometry/motion and physical behavior separately.

The local worker bounds dimensions to 0.5–500 mm and enforces recipe-specific geometric webs; these are
not strength ratings. It checks material/void probes, bounds/volume and STEP export/reimport, then writes
labeled FEASIBILITY files. STL has no embedded unit metadata; interpret these recipe exports as mm.
