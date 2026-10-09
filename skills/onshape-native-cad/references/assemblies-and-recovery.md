# Native assemblies and uncertain results

Read this for mate edits, component replacement, commanded motion or a browser timeout.

Use a fresh full feature list from the intended Assembly. For a mate, connector, group or relation,
copy a healthy native definition of the same variant and preserve its complete parameter schema.
Observed revolute definitions included limit, offset and orientation parameters beyond the two
obvious mate fields; a minimal body could return an unhealthy feature. Do not freeze a universal
parameter count. Check the current schema and adapt native queries to the intended instances.
prepare_assembly_change compares submitted parameter IDs/types with a healthy template in
that head and records a microversion precondition. Create a simple native example in the UI when
the target has no suitable healthy template. The MCP prepares JSON; the host submits it through
the session-authenticated Explorer.

After replacing a part, read the Assembly definition. Check the actual root instance's document,
element, part ID, exact configuration and version/microversion. Preserve instance IDs and inspect
affected mates. HTTP success can leave references unchanged. review_assembly_result checks
saved states, explicit root-part expectations and requested occurrence matrices at the same head.
Nested part replacements require a focused definition of their owning subassembly.

Missing feature states are UNKNOWN, including a successful complete response with an empty state
map. Explicitly suppressed recovery features are reported separately from active healthy features.
Check regenerated geometry independently; state health does not establish clearance.

For motion, record the commanded feature/value/units, fresh definition and expected matrices for
the rotating/driven and stationary components. review_assembly_motion compares these saved
samples and all baseline occurrence transforms after restoration to neutral. Matrices are row-major
with translation in metres. The command record is an operator assertion; sampled matrices are
not a continuous interference sweep, belt tracking test or physical validation.

## Submission and recovery

General native creates/updates have the same target-scoped pending protection as bounded recipes:

1. Prepare with an actual complete, unfiltered workspace head. Reobserve immediately before execution.
2. Record submitted with record_native_submission before pressing Explorer Execute.
3. If the UI times out, record result_unobserved. Preserve the existing Explorer handle and inspect
   its request URL and completed response. Never resubmit because the response was not visible.
4. Save a fresh complete feature list and use reconcile_native_change to bind the actual feature.
   It rejects unchanged heads, unmatched parameters and duplicate create candidates. Review the
   resulting feature states and geometry separately.
5. Cancel only a request that was never submitted. A saved definite matching 4xx rejection can
   release the journal; 408 and server failures remain uncertain. For 429, save retryAfter as the
   response's Retry-After duration in seconds. Honour that deadline. Do not switch authentication.

Check native_change_status before resuming old work. A reconciled manifest prohibits resubmission.
Historical requests without these journals remain recovery evidence; inspect their actual result
before preparing anything that could duplicate them. Do not edit journals to bypass uncertainty.

For large readbacks, save the completed body once and inspect bounded sections/JSON pointers.
Browser output truncation is different from an incomplete API response. A native STL can provide
appropriately scoped mesh measurements when exact BRep evidence is unavailable; record that
limitation and do not claim unobserved surfaces or interfaces.
