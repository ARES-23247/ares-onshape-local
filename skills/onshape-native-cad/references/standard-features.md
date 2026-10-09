# Planes, patterns and lofts

Use these standard native features when they resolve the actual modeling task. The local preparer
now accepts cPlane, circularPattern, linearPattern and loft. Acceptance checks transport/ownership
and journal invariants; it does not certify a feature schema or regenerated geometry.

| Task | Native approach | Focused check |
| --- | --- | --- |
| Offset mounting/profile plane | cPlane using a measured datum and named distance | Plane origin/normal and downstream profile position |
| Equal radial spokes or mounting holes | circularPattern of the intended feature/body about a native axis | Instance count, spacing and join result; test a meaningful dimension |
| Repeated straight mounting pattern | linearPattern about the intended native direction | Pitch, count and intended cut/body scope |
| Curved or changing-width guide | loft through measured ordered sketch sections | Contact-face/edge shape, solid continuity and neighboring parts |

Inspect the current Explorer specifications and a native example of the same variant. Preserve all
required parameters, resolve the target's actual queries and capture returned feature/part identities.
Do not invent region/face IDs or trim a native feature body to a minimal guessed schema.

Order construction planes before dependent sketches and sections before their loft. Keep a
feature's intended body scope explicit so a cut does not accidentally alter adjacent supports.
Supplier centerline projection followed by a constant-width extrusion may change a contact face
or finite edge; measure sections where that distinction affects the mechanism.

Expose dimensions that users need to change with native variables and sketch constraints. Verify
that a meaningful variable edit changes the actual intended interface while preserving feature IDs;
restore the selected setting. A numerically drawn editable sketch is not automatically variable-driven.

These patterns describe successful historical construction methods, not replayed API payloads for
a new target. Native queries, schemas and resulting geometry still require target-specific checks.
