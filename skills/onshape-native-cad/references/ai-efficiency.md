# Onshape AI efficiency

Cache saved model responses by exact identity: API version, document, element, version/microversion,
configuration, operation, part ID where applicable, query filters including duplicate parameters, and units.
Preserve original receipts and hashes. Immutable geometry snapshots differ from mutable workspace heads
and version metadata. Missing, altered or conflicting evidence is a cache miss.

Search local source-identified receipts before requesting new model data. Retrieve missing data through
the signed-in browser or session-authenticated official API Explorer. Before edits, observe the intended
live head and relevant fresh features. Reconcile references when it changed. After work batches, save
fresh readbacks and refresh affected dependencies. Frozen snapshots never prove current motion or fit.

The optional ares_onshape_local helper supports these operations using a local project configuration.
Use workflow_status, design_context, snapshot search/lookup and bounded JSON-pointer reads. Save
credential-free completed GET receipts; register_snapshot records operator-asserted provenance.
prepare_native_change writes a standard feature body with a source-microversion precondition and a
browser handoff manifest. Submit through your signed-in Explorer and verify actual regeneration.
The helper does not contact Onshape and does not provide browser tools or authentication.

sync_notifications ingests locally saved credential-free event JSON from the configured inbox.
Events deduplicate by message ID and mark only registered documents for refresh. Notifications carry
identifiers, not full geometry/BOM data. Save/index the subsequent session read before explicitly clearing
the refresh flag with the cache CLI. The public package does not include an internet receiver or credential
provisioning. A separately operated authenticated HTTPS receiver may save events into that inbox.

Onshape webhook notifications are exempt from annual accounting. Registering hooks, fetching changed
data, translations and completion checks follow their actual authentication route. MCP tool calls can fan
out; never assume one tool invocation equals one underlying API call.

Use built-in Advisor for documentation, descriptive public-model search for reference discovery and
Quick Render for presentation when available. Validate discovered hardware and actual geometry.
Do not bulk scrape public documents or equate generated visuals with mechanical validation.

The official Labs FeatureScript MCP is quota-consuming according to its official App Store listing. Keep it
outside this workflow unless a separate budget and task explicitly authorize it. Do not switch to API keys,
private OAuth or third-party wrappers when browser access is unavailable.

Official sources:

- [API limits](https://onshape-public.github.io/docs/auth/limits/)
- [API Explorer authentication](https://onshape-public.github.io/docs/api-intro/explorer/)
- [Webhooks](https://onshape-public.github.io/docs/app-dev/webhook/)
- [Official Labs MCP listing](https://cad.onshape.com/appstore/apps/Onshape%20Labs/6a29aea7c03f8bf659841734)
