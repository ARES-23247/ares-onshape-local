# ARES Onshape Local

This repository contains offline CAD assistance and the existing `onshape-native-cad` skill.
Keep Onshape actions in the host's signed-in browser or session-authenticated official API Explorer.
Do not add a network transport to Onshape, extract browser credentials, use API-key/private OAuth
clients, or evaluate custom FeatureScript as a fallback. The annual allowance exemption does not
remove endpoint rate limits.

Read `skills/onshape-native-cad/SKILL.md` for modeling work. Preserve actual source IDs and receipts
locally. Never commit project registries, CAD readbacks, account configurations, runtime journals,
webhook secrets, or fabrication outputs. The only checked-in geometry receipts are explicitly
anonymized historical test fixtures with synthetic source identities.

Changes to configuration or packaging require the local tests and real stdio protocol verification.
Keep arbitrary geometry programs out of the bounded recipe worker. Verify native regeneration and
required motion in Onshape before reporting CAD completion; local tests prove only their recorded scope.
