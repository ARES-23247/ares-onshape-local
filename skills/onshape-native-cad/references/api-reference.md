# Official Onshape references

Checked 2026-09-29. API versions and schemas may change; inspect the current Explorer rather than treating these routes as a complete frozen specification.

- [API Explorer](https://cad.onshape.com/glassworks/explorer/): current schemas and session-authenticated request forms.
- [API Explorer guide](https://onshape-public.github.io/docs/api-intro/explorer/): using and authenticating the Explorer.
- [API documentation](https://onshape-public.github.io/docs/): features, assemblies, model translation, configurations and authentication guides.
- [Part Studio guide](https://onshape-public.github.io/docs/api-adv/partstudios/): reading, adding and updating standard native features.
- [Configuration guide](https://onshape-public.github.io/docs/api-adv/configs/): persistent configuration definitions versus selecting a configured export.
- [API limits](https://onshape-public.github.io/docs/auth/limits/): successful API-key/private OAuth calls count; Onshape-session browser/mobile/Explorer calls do not count against the annual allowance.

## Routes to locate in the current Explorer

| Purpose | Standard route under the current `/api/vN` prefix |
| --- | --- |
| Create Part Studio | `POST /partstudios/d/{did}/w/{wid}` |
| Read native features | `GET /partstudios/d/{did}/{wvm}/{wvmid}/e/{eid}/features` |
| Read native feature specifications | `GET /partstudios/d/{did}/{wvm}/{wvmid}/e/{eid}/featurespecs` |
| Add native feature | `POST /partstudios/d/{did}/w/{wid}/e/{eid}/features` |
| Update native feature | `POST /partstudios/d/{did}/w/{wid}/e/{eid}/features/featureid/{fid}` |
| Read parts | `GET /parts/d/{did}/{wvm}/{wvmid}?elementId={eid}` |
| Read assembly definition | `GET /assemblies/d/{did}/{wvm}/{wvmid}/e/{eid}` |
| Read assembly features | `GET /assemblies/d/{did}/{wvm}/{wvmid}/e/{eid}/features` |
| Add assembly feature | `POST /assemblies/d/{did}/{wvm}/{wvmid}/e/{eid}/features` |
| Update assembly feature | `POST /assemblies/d/{did}/w/{wid}/e/{eid}/features/featureid/{fid}` |
| Read configuration definition | `GET /elements/d/{did}/{wvm}/{wvmid}/e/{eid}/configuration` |
| Update configuration definition | `POST /elements/d/{did}/w/{wid}/e/{eid}/configuration` |
| Encode configuration selection | `POST /elements/d/{did}/e/{eid}/configurationencodings` |
| Request Part Studio translation | `POST /partstudios/d/{did}/{wv}/{wvid}/e/{eid}/translations` |
| Request assembly translation | `POST /assemblies/d/{did}/{wv}/{wvid}/e/{eid}/translations` |
| Read translation status | `GET /translations/{tid}` |
| Download workspace result blob | `GET /blobelements/d/{did}/w/{wid}/e/{resultElementId}` |

These are operation locators, not a transport client. Inspect the displayed schema before submitting. Feature IDs containing `/`, `+` or other reserved characters need correct URL encoding when used in paths. `w`, `v` and `m` select workspace, version and microversion reads; do not confuse a version ID with a workspace ID.

Successful creation requires the actual native feature type, valid serialized parameters and successful regeneration. FeatureScript evaluation and Feature Studio endpoints are outside this workflow.
