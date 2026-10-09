"""Add actual project/design or read-only reference identities to a private local configuration."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
import project_config as project


def configure(config, workspace, name, document_id, workspace_id="", plan="", reference=False,
              element_ids=None, registry_source=""):
    if not project.NAME.fullmatch(name) or name == "shared" or not project.ID.fullmatch(document_id):
        raise ValueError("Use a lowercase name and actual document identity")
    root, config = Path(workspace).resolve(), Path(config).resolve()
    if not config.is_relative_to(root):
        raise ValueError("Keep private configuration inside the workspace")
    project.workspace_path(config.relative_to(root), root)
    data = json.loads(config.read_text(encoding="utf-8-sig")) if config.is_file() else {
        "project": root.name, "designs": {}, "shared_references": {}, "snapshot_dirs": ["receipts"]}
    project.reject_secrets(data)
    if registry_source:
        project.workspace_path(registry_source, root)
        data["registry_source"] = registry_source
    if reference:
        value = {"document_id": document_id}
        if workspace_id:
            if not project.ID.fullmatch(workspace_id):
                raise ValueError("Workspace identity is invalid")
            value["workspace_id"] = workspace_id
        if element_ids:
            if any(not project.ID.fullmatch(e) for e in element_ids):
                raise ValueError("Element identities are invalid")
            value["element_ids"] = element_ids
        section = "shared_references"
    else:
        if not project.ID.fullmatch(workspace_id):
            raise ValueError("A design requires its actual workspace identity")
        value = {"onshape": {"document_id": document_id, "workspace_id": workspace_id}}
        if plan:
            project.workspace_path(plan, root)
            value["plan"] = plan
        section = "designs"
    entries = data.setdefault(section, {})
    if name in entries and entries[name] != value:
        raise ValueError("An entry with this name already differs; reconcile ownership deliberately")
    entries[name] = value
    config.parent.mkdir(parents=True, exist_ok=True)
    if config.is_file():
        suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        shutil.copy2(config, config.with_name(config.name + ".ares-backup-" + suffix))
    temporary = config.with_name(config.name + ".ares-tmp")
    temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    temporary.replace(config)
    return {"config": str(config), "name": name, "read_only_reference": reference,
            "outbound_Onshape_calls": 0, "next": "Reload the MCP; reobserve the signed-in target before CAD work"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--workspace-id", default="")
    parser.add_argument("--plan", default="")
    parser.add_argument("--reference", action="store_true")
    parser.add_argument("--element-ids", nargs="*")
    parser.add_argument("--registry-source", default="")
    args = parser.parse_args()
    print(json.dumps(configure(args.config or args.workspace / "onshape-project.json", args.workspace,
        args.name, args.document_id, args.workspace_id, args.plan, args.reference, args.element_ids,
        args.registry_source), indent=2))
