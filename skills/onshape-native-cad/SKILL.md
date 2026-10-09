---
name: onshape-native-cad
description: Create or edit native parametric Onshape parts, assemblies, configurations and exports through the signed-in browser or session-authenticated official API Explorer. Use for Onshape CAD work that should avoid the annual API allowance, unless the user explicitly requests another modeling or authentication route.
---

# Native Onshape CAD

Build named native sketches, dimensions, variables/configurations, standard solid features and properly
mated assemblies. Generate exchange or fabrication exports from the regenerated Onshape model.

- Use the signed-in Onshape browser or official API Explorer authenticated by an Onshape session.
  Confirm authentication in the client. A publicly viewable document alone is not an editable session.
  Do not extract cookies, tokens or credentials into scripts or use in-page networking as a substitute.
- Authentication determines annual accounting. API-key/private OAuth clients and quota-consuming
  Onshape MCP servers are not silent fallbacks. Session-authenticated browser/Explorer calls avoid
  the annual allowance; endpoint throttles still apply. Honor 429 responses and bounded backoff.
- Do not evaluate custom FeatureScript, create/update Feature Studios or use wrappers that evaluate
  FeatureScript internally. Standard native feature request serialization and Onshape-generated query
  serialization are allowed.
- Local calculations and standard request-JSON preparation are allowed. Use local geometric previews
  only when authorized by the user or applicable project instructions. Imported custom STEP solids
  remain references until deliberately rebuilt as native features.
- Preserve stable parts, instances and mates. Create a recovery checkpoint before substantial migration
  and replace components deliberately. Reobserve the intended live workspace head before edits and
  reconcile stale feature/part/face references.

Read [references/workflow.md](references/workflow.md) for feature creation, response checks, migrations
and exports. Read [references/api-reference.md](references/api-reference.md) for official documentation
and operation locators. Use [references/templates.md](references/templates.md) when adapting the included
standard-feature JSON patterns; these require target-specific queries and current schemas.

## Purchased hardware

Use matching manufacturer CAD or established hardware libraries for purchased parts. For FRC/FTC work,
prefer available FRCDesignApp libraries such as FTCDesignLib, FRCDesignLib and MKCad when they match the
hardware. Browse/configure through the signed-in embedded panel and verify SKU, shaft/bore, hole pattern
and relevant gear/belt dimensions. Record source/configuration identities and verify insertion resolves
in the intended assembly. Reuse already verified instances and mates.

## Local assistance and verification

For authorized local part development followed by native Onshape construction, read
[references/local-part-development.md](references/local-part-development.md). Shared bounded definitions
drive local previews and native requests; they are recipes rather than an offline Onshape document format.

Read [references/assemblies-and-recovery.md](references/assemblies-and-recovery.md) for complete
mate definitions, replacement postconditions, sampled motion and recovery after uncertain submissions.

Read [references/ai-efficiency.md](references/ai-efficiency.md) for exact cache identities, saved webhook
events and the optional ares_onshape_local stdio helper. The helper prepares requests and inspects
saved receipts. It never executes Onshape actions and supplies no browser session or browser-control tool.
Use configured owning designs for edits and explicitly configured shared references for purchased-source
cache receipts. Read-only source registration does not grant edit ownership.
If browser execution is unavailable, finish useful local preparation and report that actual CAD editing
requires a browser-capable host/operator; do not switch to a quota-consuming client.

After each logical work batch, save fresh feature/assembly readbacks, inspect regeneration and verify
actual geometry and required motion in Onshape. A successful HTTP response, cached pose, healthy mate
or render alone does not prove tooth clearance, belt tracking, printed fit or physical mechanism behavior.
Keep historical evidence, native verification, physical testing and fabrication-release status distinct.

The official Labs FeatureScript MCP is outside this session-only workflow. Its App Store listing says its
calls consume API allocation. Do not infer exemption from the general public-App-Store OAuth rule.
Use an explicitly authorized separate workflow and budget if the user requests such a pilot.
