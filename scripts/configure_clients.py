"""Link the existing skill and register the local stdio server; preserve other settings."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
SERVER_NAME = "ares_onshape_local"


def backup(path):
    if path.is_file():
        target = path.with_name(path.name + ".ares-backup-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f"))
        shutil.copy2(path, target)


def link_skill(source, parent, dry_run=False):
    destination = parent / "onshape-native-cad"
    if destination.exists():
        if destination.resolve() == source.resolve():
            return {"path": str(destination), "status": "already linked"}
        raise ValueError(f"Existing skill at {destination} points elsewhere; preserve and reconcile it before installing")
    if not dry_run:
        parent.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            # Literal paths and native PowerShell end to end. No deletion or overwrite.
            quote = lambda p: "'" + str(p).replace("'", "''") + "'"
            executable = shutil.which("pwsh") or shutil.which("powershell")
            if not executable:
                raise ValueError("PowerShell is required to create a Windows directory junction")
            command = "New-Item -ItemType Junction -Path " + quote(destination) + " -Target " + quote(source) + " | Out-Null"
            subprocess.run([executable, "-NoProfile", "-NonInteractive", "-Command", command], check=True, capture_output=True,
                           creationflags=0x08000000)
        else:
            destination.symlink_to(source, target_is_directory=True)
    return {"path": str(destination), "status": "planned" if dry_run else "linked"}


def merge_server(path, entry, dry_run=False):
    data = json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file() else {}
    servers = data.setdefault("mcpServers", {})
    existing = servers.get(SERVER_NAME)
    if existing and (existing.get("command") != entry["command"] or existing.get("args") != entry["args"]):
        raise ValueError("An existing ares_onshape_local registration points elsewhere; choose the installation deliberately")
    if existing == entry:
        return "already configured"
    if not dry_run:
        backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        servers[SERVER_NAME] = {**(existing or {}), **entry}
        temporary = path.with_suffix(path.suffix + ".ares-tmp")
        temporary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
    return "planned" if dry_run else "configured"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", nargs="+", choices=("gemini", "antigravity", "claude", "codex"), default=["gemini", "antigravity", "claude"])
    parser.add_argument("--skill-source", type=Path, default=REPO / "skills/onshape-native-cad")
    parser.add_argument("--server", type=Path, default=REPO / "src/server.py")
    parser.add_argument("--python", type=Path, default=REPO / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python"))
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--project", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    source, executable, server = args.skill_source.resolve(), args.python.resolve(), args.server.resolve()
    if not (source / "SKILL.md").is_file() or not executable.is_file() or not server.is_file():
        raise ValueError("Provide an existing skill, Python interpreter with MCP installed, and server.py")
    workspace = args.workspace.resolve()
    environment = {"PYTHONUNBUFFERED": "1", "ARES_ONSHAPE_WORKSPACE": str(workspace)}
    if args.project:
        project = args.project.resolve()
        if not project.is_file():
            raise ValueError("Project configuration does not exist")
        environment["ARES_ONSHAPE_PROJECT"] = str(project)
    base = {"command": str(executable).replace("\\", "/"), "args": [str(server).replace("\\", "/")],
            "cwd": str(workspace).replace("\\", "/"), "env": environment}
    home = Path.home()
    results = []
    for client in args.clients:
        if client == "gemini":
            skill = link_skill(source, home / ".gemini/skills", args.dry_run)
            status = merge_server(home / ".gemini/settings.json", {**base, "timeout": 60000, "trust": False}, args.dry_run)
            results.append({"client": client, "skill": skill, "mcp": status, "trust_policy_changed": False})
        elif client == "antigravity":
            skills = [link_skill(source, home / path, args.dry_run) for path in
                      (".gemini/antigravity/skills", ".gemini/config/skills")]
            status = merge_server(home / ".gemini/config/mcp_config.json", {**base, "disabled": False}, args.dry_run)
            results.append({"client": client, "skills": skills, "mcp": status})
        elif client == "claude":
            skill = link_skill(source, home / ".claude/skills", args.dry_run)
            command = shutil.which("claude")
            if not command:
                raise ValueError("Install Claude Code before registering its MCP server")
            config_path = home / ".claude.json"
            data = json.loads(config_path.read_text(encoding="utf-8-sig")) if config_path.is_file() else {}
            existing = data.get("mcpServers", {}).get(SERVER_NAME)
            if existing:
                same_command = Path(existing.get("command", "")).resolve() == executable
                same_arguments = len(existing.get("args", [])) == 1 and Path(existing["args"][0]).resolve() == server
                if not same_command or not same_arguments:
                    raise ValueError("Existing Claude MCP registration points elsewhere; preserve and reconcile it")
                status = "already configured"
            elif args.dry_run:
                status = "planned"
            else:
                backup(config_path)
                # Use the client's official command rather than changing its credential-bearing config.
                # The positional name precedes variadic --env options; otherwise it is consumed as env.
                command_args = [command, "mcp", "add", "--scope", "user", "--transport", "stdio", SERVER_NAME]
                for key, value in environment.items():
                    command_args += ["--env", f"{key}={value}"]
                command_args += ["--", str(executable), str(server)]
                process = subprocess.run(command_args, capture_output=True, text=True,
                                         creationflags=0x08000000 if os.name == "nt" else 0)
                if process.returncode:
                    raise ValueError("Claude MCP registration failed; inspect locally with claude mcp list")
                status = "configured"
            results.append({"client": client, "skill": skill, "mcp": status})
        else:
            results.append({"client": client, "skill": link_skill(source, home / ".codex/skills", args.dry_run),
                            "mcp": "Use codex mcp add ares_onshape_local -- <python> <server.py>; existing Codex settings are preserved"})
    print(json.dumps({"results": results, "outbound_Onshape_calls": 0,
                      "runtime_execution_verified": False, "browser_session_supplied": False}, indent=2))


if __name__ == "__main__":
    main()
