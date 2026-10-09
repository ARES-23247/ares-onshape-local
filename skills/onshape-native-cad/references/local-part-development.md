# Local part development

Use local studies when authorized, then create the selected final part as native Onshape features.
Onshape documents live in its cloud database; there is no supported offline native file to generate and
upload with full feature history. STEP/Parasolid imports provide solids for reference or direct editing,
without the source feature tree. A saved local recipe can instead drive both the preview and native
construction. This requires the host's signed-in browser/session-authenticated Explorer.

With ares_onshape_local, use save_part_definition to save a bounded family, millimetre dimensions,
label and owning design. preview_part_definition produces an inspectable FEASIBILITY bundle with
geometry checks, STEP roundtrip and experimental STL. prepare_part_definition binds that exact source
and optional preview_record to a fresh empty native Part Studio head. A changed source or artifact fails
hash checks. The native compiler is pinned to its validated API/library revision; do not bypass a revision
mismatch or transplant cached feature IDs into a new target.

Supported families are spacer, mounting_bracket, hole_pattern_plate, flanged_hub, radial_hole_plate
and lofted_guide. The first three have historical live native pilot evidence. The added hub, radial plate
and lofted guide have local geometry and simulated request checks; verify actual native regeneration
and a meaningful parameter edit before reporting their native CAD complete. The radial plate has six
fixed holes. Guide wall is an inset in each XY section, not a constant normal wall thickness.

prepare_recipe_step resolves actual returned feature references and writes one standard native request.
Reobserve the head before browser submission, save the actual fresh feature list and bind_recipe_step.
Use part_development_status to resume. A pending request requires actual readback; do not blindly retry.
Separate target Part Studios keep experiments recoverable and avoid changing validated assemblies.

After construction, verify_native_recipe requires bodydetails and massproperties at the same observed
immutable microversion. It compares surfaces, hole locations, bounds, areas and volume with the recipe.
An attached local preview must still match its saved definition/artifacts. Observe live geometry as well.

For a parameter test, save a revised definition, call prepare_part_definition with manifest_source and
a fresh head (plus the revised preview when needed), submit and bind the existing-variable update,
then verify changed geometry. verify_part_parameter_change checks two recorded geometry reports and
stable native feature IDs. Preserve the baseline report and deliberately restore selected dimensions
after experimentation. An unchanged-dimension definition does not replace the current journal binding.

These tools generate standard variables, constrained sketches, extrusions, a full revolve, construction
plane, circular face pattern and ordered lofts. They do not translate arbitrary FreeCAD/build123d programs,
recover STEP history, evaluate FeatureScript, execute native requests or prove physical fit/load capacity.

Official sources: [Onshape database architecture](https://www.onshape.com/en/blog/data-management-comparing-cad-files-and-databases),
[import feature-history limitations](https://cad.onshape.com/help/Content/Document/importing_files.htm),
[standard feature APIs](https://onshape-public.github.io/docs/api-adv/featureaccess/).
