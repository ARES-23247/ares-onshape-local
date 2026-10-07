# Modeling workflow

## Establish the target

Read the intended document, workspace and element from the user or current model. Record `did`, `wid`, `eid` and component/feature IDs in the task workspace, not in this global reference. Use a workspace for edits. Confirm a signed-in editable session; a publicly viewable document is not evidence of authentication.

Create a recovery version before a substantial migration. Preserve existing stable parts and assembly instances while constructing native replacements in clearly named Part Studios.

## Build native features

Use named sketches and ordinary native features. Prefer dimensions and variables/configuration inputs for meaningful design changes. Read the target's feature specifications and a known native feature definition when a parameter or enum is uncertain; do not guess unsupported parameter names. A sketch with fixed numerical geometry alone is editable, but does not establish that all intended design parameters drive the model.

Prepare request JSON locally if useful, then submit it through the session-authenticated API Explorer UI. This reference does not authorize key-authenticated Python HTTP calls or cookie extraction. Native feature JSON is the serialization of standard Onshape operations; it is distinct from a custom FeatureScript program or evaluation call.

Check the returned `featureState.featureStatus` and then a fresh feature-tree readback. Capture actual resulting IDs. A 2xx HTTP status alone does not prove successful regeneration. Stop dependent operations when a feature fails, inspect the specific error and repair that feature.

For updates, retain the feature's type, name, ID and unaffected parameters from a fresh readback. Updating a single dimension does not justify submitting a guessed partial feature definition. Native cloud modeling still requires robust references and regeneration checks; it does not eliminate topology-dependent failures.

## Verify browser responses

Explorer Execute starts a request asynchronously. A previous response can remain visible while the new call runs. Verify the displayed request URL and a completed, fresh response before interpreting it. For updates, compare expected feature IDs, names and source microversions. After a timeout, read back the model before retrying a mutation, to avoid duplicate parts or features.

Keep responses compact when inspecting large assemblies. Disable thumbnails for part inventories. Save useful response bodies locally, but do not capture or print authorization/cookie/XSRF headers. Do not inspect hidden application state or use in-page networking to bypass supported browser operations.

## Assemblies and migration

Preserve instance IDs where feasible and check mates after replacements. Ground the stationary structure; use fastened/group constraints for rigid hardware and revolute/slider/cylindrical mates as appropriate for real motion. Set actual travel/rotation limits and gear relations. Rigid imports or a visually correct pose are not proof of proper degrees of freedom.

Imported component identities can change during source-file replacement, even when labels or body counts look unchanged. Verify component names, resolved part references, owner paths, mate states and motion. Do not declare a broken assembly complete. Recover a known working version if a migration cannot be repaired reliably, preserve the attempted work separately, and report the actual state.

## Configure and export

Distinguish a variable feature from a configuration definition and from a configuration selection. Update the appropriate native feature or configuration definition for a persistent model change. Supplying a configuration string on an export selects an existing configuration; it does not rewrite the configuration table.

After regeneration succeeds, request a STEP/STL translation from the intended Part Studio or assembly. Save its translation ID, poll with reasonable backoff, and handle `ACTIVE`, `DONE` and `FAILED`. Download using the returned external-data reference or supported browser download. Check that the export is for the intended element/configuration and is nonempty; do not claim an export completed while a translation is still active.

## Limits and failure handling

Use official documentation to distinguish annual allowance from endpoint throttling. Honor 429 responses and bounded retry/backoff; do not treat a rate-limit reset as permission to switch authentication. Ask for sign-in only after the session is confirmed expired. Do not silently change modeling or authentication pipelines because browser access is unavailable.
