"""Local project configuration. No credentials, browser access, or outbound requests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re

EXPLICIT_CONFIG = os.environ.get("ARES_ONSHAPE_PROJECT")
CONFIG = Path(EXPLICIT_CONFIG).expanduser().resolve() if EXPLICIT_CONFIG else Path.cwd() / "onshape-project.json"
WORKSPACE = Path(os.environ.get("ARES_ONSHAPE_WORKSPACE", CONFIG.parent)).expanduser().resolve()
ID = re.compile(r"[0-9a-f]{24}")
NAME = re.compile(r"[a-z][a-z0-9-]{0,63}")
SECRET_KEYS = {"authorization", "cookie", "setcookie", "password", "apikey", "secretkey",
               "accesskey", "accesstoken", "refreshtoken", "clientsecret", "xsrftoken", "csrftoken"}


def reject_secrets(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if re.sub(r"[^a-z]", "", str(key).lower()) in SECRET_KEYS:
                raise ValueError("Project configuration must not contain credentials")
            reject_secrets(child)
    elif isinstance(value, list):
        for child in value:
            reject_secrets(child)


def workspace_path(value, workspace=WORKSPACE):
    root = Path(workspace).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Project paths must stay inside the configured workspace")
    if any(part.lower() in {".git", ".codex", ".claude", ".gemini", ".agents", ".venv", "node_modules"}
           for part in path.relative_to(root).parts):
        raise ValueError("Project data must stay outside account, Git and dependency internals")
    return path


def registry_path(workspace=WORKSPACE):
    root = Path(workspace).resolve()
    return CONFIG if root == WORKSPACE else root / "onshape-project.json"


def read_registry(workspace=WORKSPACE):
    path = registry_path(workspace)
    if not path.is_file():
        if EXPLICIT_CONFIG and Path(workspace).resolve() == WORKSPACE:
            raise ValueError("The explicit ARES_ONSHAPE_PROJECT configuration does not exist")
        return {"project": "Unconfigured local workspace", "designs": {}, "shared_references": {}}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    reject_secrets(data)
    if not isinstance(data, dict) or not isinstance(data.get("project"), str) or not isinstance(data.get("designs"), dict):
        raise ValueError("Project configuration requires project and designs")
    data.setdefault("shared_references", {})
    if not isinstance(data["shared_references"], dict):
        raise ValueError("shared_references must be an object")
    for name, design in data["designs"].items():
        if not NAME.fullmatch(name) or name == "shared" or not isinstance(design, dict):
            raise ValueError("Design names must be lowercase identifiers; shared is reserved")
        native = design.get("onshape", {})
        if not all(isinstance(native.get(k), str) and ID.fullmatch(native[k]) for k in ("document_id", "workspace_id")):
            raise ValueError("Each design needs actual document_id and workspace_id values")
        if not isinstance(native.get("recovery_elements", []), list):
            raise ValueError("recovery_elements must be an array")
        for element in native.get("recovery_elements", []):
            if not isinstance(element, str) or not ID.fullmatch(element):
                raise ValueError("Recovery element identities must be valid Onshape IDs")
        if design.get("plan"):
            workspace_path(design["plan"], workspace)
    for value in data["shared_references"].values():
        if not isinstance(value, dict) or not isinstance(value.get("document_id"), str) or not ID.fullmatch(value["document_id"]):
            raise ValueError("Shared references need actual document identities")
    if not isinstance(data.get("snapshot_dirs", ["receipts"]), list):
        raise ValueError("snapshot_dirs must be an array")
    for directory in data.get("snapshot_dirs", ["receipts"]):
        if not isinstance(directory, str):
            raise ValueError("snapshot_dirs entries must be paths")
        workspace_path(directory, workspace)
    for key in ("runtime_dir", "event_dir"):
        if data.get(key):
            workspace_path(data[key], workspace)
    return data


def runtime_path(child="", workspace=WORKSPACE):
    directory = read_registry(workspace).get("runtime_dir", ".ares-onshape")
    return workspace_path(Path(directory) / child, workspace)
