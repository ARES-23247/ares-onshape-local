# ARES Onshape Local

Version 0.2 adds complete-template Assembly preparation, saved reference/pose review, general
pending-operation reconciliation, read-only external-source caching and native plane/pattern/loft support.
All Onshape execution remains in the host's signed-in browser/session Explorer.

Local MCP tools and the existing `onshape-native-cad` skill for native editable Onshape CAD through a
signed-in browser or session-authenticated official API Explorer. Supports stdio MCP clients including
Codex, Gemini CLI, Google Antigravity and Claude Code.

The server makes **zero outbound Onshape requests**. It searches saved responses, prepares standard
native feature JSON, tracks recipe operations and checks saved results. Your agent or operator executes
CAD requests using its own browser tools and Onshape session. Installing this package supplies neither.

This route avoids the **annual API-call allowance**, not all limits. Endpoint throttles still apply.
Successful API-key/private OAuth requests and API Explorer requests using those modes consume
allocation. See [Onshape's accounting rules](https://onshape-public.github.io/docs/auth/limits/).

## Install

Use Python 3.12 or newer. Clone this repository and create a dedicated environment:

```powershell
git clone https://github.com/ARES-23247/ares-onshape-local.git
Set-Location ares-onshape-local
py -3.12 -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r requirements.txt
& ./.venv/Scripts/python.exe scripts/configure_clients.py --dry-run
& ./.venv/Scripts/python.exe scripts/configure_clients.py
```

On Linux/macOS use `python3 -m venv .venv` and `.venv/bin/python` for the Python commands.
The default installer links the same skill into Gemini, Antigravity and Claude Code, preserving unrelated
settings and server definitions. Changed JSON files are backed up beside their originals; backups may
contain account secrets and must remain local. It stops rather than overwrite a skill/server pointing at
another installation. Review `--dry-run` first. Client trust/approval policies are preserved.

Restart/reload MCP and skill discovery in each client. Do not globally trust tools or enable API-key or
FeatureScript servers to work around a connection failure.

| Client | Skill location | MCP registration |
| --- | --- | --- |
| Gemini CLI | `~/.gemini/skills/onshape-native-cad` | `~/.gemini/settings.json` |
| Antigravity IDE | `~/.gemini/antigravity/skills/onshape-native-cad` | `~/.gemini/config/mcp_config.json` |
| Antigravity 2.0 | `~/.gemini/config/skills/onshape-native-cad` | Same local MCP configuration |
| Claude Code | `~/.claude/skills/onshape-native-cad` | Official `claude mcp add --scope user` |
| Codex | `~/.codex/skills/onshape-native-cad` | Official `codex mcp add` |

Select clients with `--clients`; the default is Gemini, Antigravity and Claude. To link the Codex skill:

```powershell
& ./.venv/Scripts/python.exe scripts/configure_clients.py --clients codex
codex mcp add ares_onshape_local -- <absolute-python-path> <absolute-path-to-src/server.py>
```

For a working local installation, use `--skill-source`, `--python`, `--server` and `--workspace` to
link/register that installation without copying the skill or replacing its source. Claude Code must be
installed for its registration step. Antigravity CLI uses another skill path: install the same folder in
`~/.gemini/antigravity-cli/skills` and register stdio in that client if you use that surface.
See [Gemini](https://geminicli.com/docs/cli/skills/),
[Antigravity](https://antigravity.google/docs/skills) and
[Claude Code](https://code.claude.com/docs/en/skills) discovery documentation.

## Select a workspace

With no configuration, calculators, recipe discovery and separate-sandbox native recipe preparation
remain available. Named-design tools require a registry. Copy `examples/onshape-project.example.json`
to **your CAD workspace** as `onshape-project.json`, replace synthetic document/workspace IDs with
actual ones and keep it private. Plans, receipt directories, runtime output and event inbox paths must
remain inside that workspace.

```powershell
& ./.venv/Scripts/python.exe scripts/configure_clients.py --workspace <CAD-workspace> --project <CAD-workspace>/onshape-project.json
```

Or configure the stdio command directly:

```json
{
  "mcpServers": {
    "ares_onshape_local": {
      "command": "<absolute Python executable with MCP installed>",
      "args": ["<absolute path to src/server.py>"],
      "env": {
        "ARES_ONSHAPE_WORKSPACE": "<absolute CAD workspace>",
        "ARES_ONSHAPE_PROJECT": "<absolute local onshape-project.json>"
      }
    }
  }
}
```

If moving an existing registration to another server, reconcile that client entry explicitly; the installer
preserves conflicts. Enterprise-specific Onshape hostnames are not supported in this version: receipt
routes are restricted to `cad.onshape.com`.

## Use

To add a standalone part or another robot, run scripts/configure_project.py with --workspace,
--name, --document-id and --workspace-id, plus --plan when applicable. Use --reference instead
for a read-only library/source document, optionally bounded by --element-ids. Supply actual source
identities; the helper never discovers or creates a live CAD document. Reload the MCP after configuration.

An existing private registry can remain authoritative: set registry_source to its workspace-relative
JSON path in onshape-project.json. Its current designs are merged with additional local entries.
Prose-only reference entries are ignored; configured document references retain read-only scope.
catalog_path can point to the existing workspace SQLite catalog, and runtime_dir can preserve existing
journals. Neither configuration nor receipts belong in Git. Keep one maintained core and skill source;
use a local compatibility entrypoint for private receiver integration instead of copying implementation.

1. Read `workflow_status` and the owning `design_context`. Search snapshots and lookup exact immutable
   GET identities before new model reads. Workspace reads always miss the exact cache.
2. Save completed session reads as credential-free JSON receipts. Register with explicit operator
   confirmation; the server cannot independently prove their browser origin.
3. Save a fresh workspace feature-list receipt and call `prepare_native_change`. Reobserve the live head
   immediately before submitting its prepared body through signed-in Explorer.
4. Save fresh readbacks and check native feature states, geometry and required motion in Onshape.
   A successful POST or healthy saved state alone does not prove mechanical behavior or release readiness.

See [receipts and tools](docs/tools.md), [native recipe scope](docs/native-recipes.md) and the
[Onshape skill](skills/onshape-native-cad/SKILL.md).

`sync_notifications` ingests saved, credential-free webhook events from a configured local directory.
It deduplicates events and queues affected registered documents for refresh, with no outbound network.
A public HTTPS receiver, authentication and event delivery must be provided separately.

## Optional geometry previews

The spacer, L mounting bracket and four-hole plate generate bounded build123d FEASIBILITY previews
when local geometry is authorized for your project:

```powershell
py -3.12 -m venv .venv-build123d
& ./.venv-build123d/Scripts/python.exe -m pip install -r requirements-build123d.txt
```

Use `ARES_ONSHAPE_CAD_PYTHON` for another compatible isolated Python executable. The worker accepts
only these three recipes, rejects arbitrary code and blocks Python socket operations. STEP/STL are
temporary references or experimental prints. Final custom CAD needs native Onshape features and actual
regeneration. The compiler profile is pinned and rejects unvalidated Onshape revisions.

## Validate

```powershell
& ./.venv/Scripts/python.exe -m unittest discover -s src -p "test_*.py" -v
& ./.venv/Scripts/python.exe scripts/verify_mcp.py
& ./.venv-build123d/Scripts/python.exe -m unittest discover -s src -p "test_*.py" -v
& ./.venv/Scripts/python.exe scripts/verify_mcp.py --geometry
```

The last two commands require the optional build123d environment. Tests skip geometry when unavailable. Protocol verification
starts the actual server over stdio in an isolated synthetic workspace and makes no Onshape calls.
Anonymized historical geometry fixtures are test evidence, not current browser authentication, live CAD
regeneration, assembly motion or physical fit verification.

Public source excludes robot plans, live receipts, account settings, secrets, private CAD and runtime
outputs. Preserve those exclusions when contributing.
