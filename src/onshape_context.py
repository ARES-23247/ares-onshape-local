"""Offline Onshape response catalog. No outbound HTTP or Onshape credentials."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import parse_qsl, urlencode, urlsplit

import project_config as project

ROOT = project.WORKSPACE
DEFAULT_DB = (project.workspace_path(project.read_registry()["catalog_path"])
              if project.read_registry().get("catalog_path") else project.runtime_path("cache.sqlite3"))
SCHEMA_VERSION = 1
SENSITIVE = {"authorization", "cookie", "setcookie", "password", "accesskey",
             "secretkey", "accesstoken", "refreshtoken", "xsrftoken", "csrftoken"}
ID = re.compile(r"^[0-9a-f]{24}$")
ROUTE = re.compile(r"/d/([0-9a-f]{24})/(w|v|m)/([0-9a-f]{24})(?:/e/([0-9a-f]{24}))?")
URL_KEYS = ("requestUrl", "request_url", "executed_url", "executedUrl", "url")
OWNERS = tuple(project.read_registry()["designs"]) + ("shared",)


def now():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sensitive(value):
    if isinstance(value, dict):
        return any(re.sub(r"[^a-z]", "", str(k).lower()) in SENSITIVE or sensitive(v)
                   for k, v in value.items())
    if isinstance(value, list):
        return any(sensitive(v) for v in value)
    return False


def identity(url, units="m"):
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password:
        raise ValueError("Expected an HTTPS Onshape request URL without credentials")
    if parsed.hostname != "cad.onshape.com":
        raise ValueError("This catalog accepts cad.onshape.com only")
    if parsed.fragment:
        raise ValueError("API request URLs must not contain fragments")
    # Ordering between different keys is immaterial; repeated-key order may matter.
    pairs = sorted(parse_qsl(parsed.query, keep_blank_values=True), key=lambda pair: pair[0])
    if any(re.sub(r"[^a-z]", "", k.lower()) in SENSITIVE for k, _ in pairs):
        raise ValueError("Credential-bearing query rejected")
    route = ROUTE.search(parsed.path)
    if not route:
        raise ValueError("Request has no document/workspace/version/microversion identity")
    did, context_type, context_id, eid = route.groups()
    part = re.search(r"/partid/([^/]+)", parsed.path)
    fields = {"method": "GET", "host": parsed.netloc.lower(), "path": parsed.path,
              "query": pairs, "units": units}
    return {"key": digest(canonical(fields).encode()), "request": fields,
            "url": f"https://{parsed.netloc.lower()}{parsed.path}" +
                   ("?" + urlencode(pairs) if pairs else ""),
            "document_id": did, "element_id": eid or "", "context_type": context_type,
            "context_id": context_id,
            "configuration": next((v for k, v in pairs if k == "configuration"), "__unspecified__"),
            "part_id": part.group(1) if part else "", "units": units,
            "operation": parsed.path[route.end():] or parsed.path.split("/d/")[0].split("/")[-1],
            "immutable_geometry": context_type in ("m", "v")}


def connect(path=DEFAULT_DB):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS artifacts (
      path TEXT PRIMARY KEY, file_hash TEXT NOT NULL, payload_hash TEXT NOT NULL,
      owner TEXT NOT NULL, identity_json TEXT NOT NULL, request_key TEXT,
      document_id TEXT NOT NULL, element_id TEXT NOT NULL, context_id TEXT NOT NULL,
      operation TEXT NOT NULL, indexed_at TEXT NOT NULL, search_text TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS request_index ON artifacts(request_key);
    CREATE INDEX IF NOT EXISTS owner_index ON artifacts(owner);
    CREATE TABLE IF NOT EXISTS counters (name TEXT PRIMARY KEY, value INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS refresh_events (
      message_id TEXT PRIMARY KEY, document_id TEXT NOT NULL, event TEXT NOT NULL,
      received_at TEXT NOT NULL, payload_json TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS refresh_state (
      document_id TEXT PRIMARY KEY, dirty INTEGER NOT NULL, reason TEXT NOT NULL,
      observed_head TEXT, refreshed_at TEXT
    );
    CREATE TABLE IF NOT EXISTS usage (
      id INTEGER PRIMARY KEY, recorded_at TEXT NOT NULL, transport TEXT NOT NULL,
      status INTEGER NOT NULL, note TEXT NOT NULL
    );
    """)
    return db


def count(db, name):
    db.execute("INSERT INTO counters VALUES (?,1) ON CONFLICT(name) DO UPDATE SET value=value+1", (name,))


def owner_for(path, document_id=None, registry=None, element_id=None):
    if registry and document_id:
        for owner, design in registry["designs"].items():
            if design.get("onshape", {}).get("document_id") == document_id:
                return owner
    return "shared"


def payload_for(data):
    if not isinstance(data, dict):
        return data
    if "bounds" in data and any(k in data for k in URL_KEYS):
        return data["bounds"]
    for key in ("response", "responseBody", "response_body", "body"):
        if isinstance(data.get(key), (dict, list)):
            return data[key]
    return {k: v for k, v in data.items()
            if k not in (*URL_KEYS, "httpStatus", "date", "transport", "headers", "requestHeaders")}


def infer(data):
    if not isinstance(data, dict) or sensitive(data):
        return None
    status = data.get("httpStatus", data.get("statusCode", 200))
    if isinstance(status, int) and not 200 <= status < 300:
        return None
    for key in URL_KEYS:
        url = data.get(key)
        if isinstance(url, str) and "onshape.com/api/" in url:
            # A saved request body is not a read response. Require evidence of a response.
            if not any(k in data for k in ("bounds", "response", "body", "responseBody", "response_body", "httpStatus", "statusCode")):
                continue
            method = data.get("method", data.get("requestMethod", "GET")).upper()
            if method != "GET":
                continue
            try:
                ident = identity(url, data.get("units", "m"))
            except (ValueError, TypeError):
                continue
            if any(segment in urlsplit(url).path for segment in ("featurescript", "translations", "/featurestudios/")):
                continue
            root = payload_for(data)
            source = data.get("source")
            if isinstance(source, dict):
                for source_key, expected in (("documentId", ident["document_id"]), ("elementId", ident["element_id"])):
                    if source.get(source_key) and source[source_key] != expected:
                        return None
                if ident["context_type"] == "m" and source.get("documentMicroversion") and source["documentMicroversion"] != ident["context_id"]:
                    return None
            if isinstance(root, dict) and ident["context_type"] == "m" and root.get("sourceMicroversion"):
                if root["sourceMicroversion"] != ident["context_id"]:
                    return None
            if isinstance(root, dict) and isinstance(root.get("rootAssembly"), dict):
                actual = root["rootAssembly"]
                if actual.get("documentId") != ident["document_id"] or actual.get("elementId") != ident["element_id"]:
                    return None
                if ident["context_type"] == "m" and actual.get("documentMicroversion") != ident["context_id"]:
                    return None
            ident["capture"] = "saved-read-response"
            ident["transport_evidence"] = data.get("transport", "not recorded")
            return ident, root, ident["key"] if ident["immutable_geometry"] else None
    root = data.get("rootAssembly")
    if isinstance(root, dict) and all(ID.fullmatch(str(root.get(k, "")))
                                      for k in ("documentId", "elementId", "documentMicroversion")):
        ident = {"document_id": root["documentId"], "element_id": root["elementId"],
                 "context_type": "m", "context_id": root["documentMicroversion"],
                 "configuration": root.get("fullConfiguration", root.get("configuration", "__unspecified__")),
                 "operation": "assembly-definition", "units": "m", "immutable_geometry": True,
                 "capture": "raw-assembly-response; request options unknown", "url": None,
                 "transport_evidence": "not recorded in this file"}
        # Raw snapshots support offline reasoning; do not invent an executed URL or filters.
        return ident, data, None
    return None


def index_files(db, roots, workspace=ROOT):
    stats = Counter()
    registry_path = project.registry_path(workspace)
    registry = project.read_registry(workspace)
    for root in roots:
        for path in sorted(Path(root).rglob("*.json")):
            if not path.resolve().is_relative_to(workspace.resolve()):
                raise ValueError("Index inputs must stay inside the workspace")
            if path.stat().st_size > 25 * 1024 * 1024:
                stats["skipped_large"] += 1
                continue
            stats["scanned"] += 1
            raw = path.read_bytes()
            try:
                data = json.loads(raw.decode("utf-8-sig"))
                result = infer(data)
            except (ValueError, TypeError, AttributeError):
                stats["skipped_unrecognized"] += 1
                continue
            if result is None:
                stats["skipped_unrecognized"] += 1
                continue
            ident, payload, key = result
            try:
                relative = path.resolve().relative_to(workspace.resolve()).as_posix()
            except ValueError:
                raise ValueError("Index inputs must stay inside the workspace")
            metadata = canonical(ident)
            source = data.get("source")
            text = " ".join((relative, metadata, str(source.get("name", "")) if isinstance(source, dict) else ""))
            db.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                       (relative, digest(raw), digest(canonical(payload).encode()), owner_for(Path(relative), ident["document_id"], registry, ident["element_id"]),
                        metadata, key, ident["document_id"], ident["element_id"], ident["context_id"],
                        ident["operation"], now(), text))
            stats["indexed"] += 1
            stats["exact_request_records" if key else "context_only_records"] += 1
            if stats["indexed"] % 50 == 0:
                db.commit()
    db.commit()
    return dict(stats)


def add_response(db, path, url, owner, units="m", confirmed=False, workspace=ROOT):
    """Register a raw response using its explicitly recorded executed URL."""
    if not confirmed:
        raise ValueError("Supply --confirmed-response only for an actual completed GET response")
    path = Path(path).resolve()
    if not path.is_relative_to(workspace.resolve()):
        raise ValueError("Response must stay inside the workspace")
    ident = identity(url, units)
    data = read_json(path)
    if sensitive(data):
        raise ValueError("Credential-bearing response rejected")
    checked = infer({"requestUrl": url, "httpStatus": 200, "response": data, "units": units})
    if checked is None:
        raise ValueError("Response source or operation does not match the supplied GET URL")
    ident, payload, key = checked
    ident["capture"] = "raw response; operator-confirmed executed GET URL"
    relative = path.relative_to(workspace.resolve()).as_posix()
    db.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
               (relative, digest(path.read_bytes()), digest(canonical(payload).encode()), owner,
                canonical(ident), key, ident["document_id"], ident["element_id"], ident["context_id"],
                ident["operation"], now(), " ".join((relative, canonical(ident)))))
    db.commit()
    return {"registered": relative, "identity": ident}


def index_linked_provenance(db, path, workspace=ROOT):
    """Index hashes/identities explicitly bound by a saved provenance checkpoint."""
    evidence = read_json(path)
    did, eid = evidence["document_id"], evidence["element_id"]
    if not ID.fullmatch(did) or not ID.fullmatch(eid):
        raise ValueError("Invalid provenance identity")
    registered = 0
    for label, record in evidence["raw_readbacks"].items():
        raw_path = path.parent / record["file"]
        if not raw_path.resolve().is_relative_to(workspace.resolve()):
            raise ValueError("Provenance points outside the workspace")
        if digest(raw_path.read_bytes()) != record["sha256"]:
            raise ValueError("Provenance hash mismatch")
        payload = read_json(raw_path)
        if sensitive(payload) or payload.get("sourceMicroversion") != record["microversion"]:
            raise ValueError("Provenance microversion mismatch")
        ident = {"document_id": did, "element_id": eid, "context_type": "m",
                 "context_id": record["microversion"], "configuration": "__unspecified__",
                 "operation": "feature-list", "units": "m", "immutable_geometry": True,
                 "url": None, "capture": "hash-bound feature readback; request filters unknown",
                 "provenance_file": path.relative_to(workspace).as_posix(), "provenance_label": label,
                 "provenance_sha256": digest(path.read_bytes()),
                 "transport_evidence": evidence.get("transport", "not recorded")}
        relative = raw_path.relative_to(workspace).as_posix()
        owner = evidence["design"]
        if owner not in OWNERS:
            raise ValueError("Invalid design owner")
        db.execute("INSERT OR REPLACE INTO artifacts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (relative, record["sha256"], digest(canonical(payload).encode()), owner, canonical(ident), None,
                    did, eid, record["microversion"], "feature-list", now(), relative + " " + canonical(ident)))
        registered += 1
    db.commit()
    return {"provenance_readbacks_indexed": registered}


def lookup(db, url, units="m", workspace=ROOT):
    ident = identity(url, units)
    if not ident["immutable_geometry"]:
        count(db, "misses")
        db.commit()
        return {"hit": False, "reason": "Workspace reads require fresh session observation", "identity": ident}
    rows = db.execute("SELECT * FROM artifacts WHERE request_key=? ORDER BY path", (ident["key"],)).fetchall()
    valid = []
    for row in rows:
        path = workspace / row["path"]
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if digest(raw) != row["file_hash"]:
            continue
        valid.append((row, raw))
    if not valid or len({row["payload_hash"] for row, _ in valid}) != 1:
        count(db, "misses")
        db.commit()
        return {"hit": False, "reason": "Missing, modified or conflicting saved response", "identity": ident}
    row, raw = valid[0]
    data = json.loads(raw.decode("utf-8-sig"))
    count(db, "hits")
    db.commit()
    return {"hit": True, "source": row["path"], "file_sha256": row["file_hash"],
            "identity": json.loads(row["identity_json"]), "payload": payload_for(data),
            "scope": "Historical frozen response; no current regeneration, motion or physical verification"}


def search(db, query, owner=None, limit=20):
    terms = query.lower().split()
    rows = db.execute("SELECT * FROM artifacts" + (" WHERE owner=?" if owner else "") + " ORDER BY path",
                      (owner,) if owner else ()).fetchall()
    hits = [r for r in rows if all(t in r["search_text"].lower() for t in terms)]
    return {"total_matches": len(hits), "results": [
        {"source": r["path"], "owner": r["owner"], "file_sha256": r["file_hash"],
         "identity": json.loads(r["identity_json"])} for r in hits[:limit]]}


def context(db, design, workspace=ROOT):
    registry_path = project.registry_path(workspace)
    registry = project.read_registry(workspace)
    design_data = registry["designs"][design]
    plan = project.workspace_path(design_data["plan"], workspace) if design_data.get("plan") else None
    rows = db.execute("SELECT owner,operation,COUNT(*) n FROM artifacts WHERE owner IN (?, 'shared') GROUP BY owner,operation", (design,)).fetchall()
    native = design_data.get("onshape", {})
    return {"schema_version": SCHEMA_VERSION, "design": design, "generated_at": now(),
            "scope": "Offline catalog and recorded identities; no live-head freshness or verification implied",
            "plan": design_data.get("plan"), "plan_sha256": digest(plan.read_bytes()) if plan and plan.is_file() else None,
            "registry_sha256": digest(registry_path.read_bytes()) if registry_path.is_file() else None,
            "authoritative_destination": {k: native[k] for k in
                ("document_id", "workspace_id", "current_integration_element_id", "native_assembly_element_id",
                 "current_part_studio_element_id") if k in native},
            "recorded_recovery": {k: native[k] for k in ("recovery_version_id", "recovery_microversion") if k in native},
            "shared_references": registry["shared_references"],
            "catalog_counts": [dict(r) for r in rows],
            "refresh_queue": [dict(r) for r in db.execute("SELECT * FROM refresh_state WHERE dirty=1")],
            "next": "Search this design and shared references; lookup exact immutable GET URLs before any new read. Revalidate live head before edits."}


def ingest_event(db, event, registry=None):
    if not isinstance(event, dict) or sensitive(event):
        raise ValueError("Expected a credential-free webhook JSON object")
    kind = event.get("event")
    message = event.get("messageId")
    did = event.get("documentId")
    if not isinstance(kind, str) or not isinstance(message, str) or not message:
        raise ValueError("Webhook requires event and messageId")
    if kind not in ("webhook.register", "webhook.ping", "webhook.unregister"):
        if not isinstance(did, str) or not ID.fullmatch(did):
            raise ValueError("Model event requires a valid documentId")
        if registry is not None:
            allowed = {v["onshape"]["document_id"] for v in registry["designs"].values()}
            allowed |= {v["document_id"] for v in registry["shared_references"].values()
                        if isinstance(v, dict) and "document_id" in v}
            if did not in allowed:
                raise ValueError("Webhook document is outside the configured project registry")
    with db:
        inserted = db.execute("INSERT OR IGNORE INTO refresh_events VALUES (?,?,?,?,?)",
                              (message, did or "", kind, now(), canonical(event))).rowcount
        if inserted and kind not in ("webhook.register", "webhook.ping", "webhook.unregister"):
            db.execute("INSERT INTO refresh_state VALUES (?,1,?,NULL,NULL) ON CONFLICT(document_id) DO UPDATE SET dirty=1,reason=excluded.reason",
                       (did, kind))
    return {"accepted": True, "duplicate": not bool(inserted),
            "refresh_required": bool(did and not kind.startswith("webhook.")), "outbound_calls": 0}


def refresh_complete(db, did, head, confirmed):
    if not confirmed or not ID.fullmatch(head) or not ID.fullmatch(did):
        raise ValueError("Supply --confirmed-session-read and a real observed document/head identity")
    with db:
        db.execute("INSERT INTO refresh_state VALUES (?,0,'session refresh recorded',?,?) ON CONFLICT(document_id) DO UPDATE SET dirty=0,reason=excluded.reason,observed_head=excluded.observed_head,refreshed_at=excluded.refreshed_at",
                   (did, head, now()))
    return {"recorded": True, "verification": "Operator assertion of session refresh; not automated geometry verification"}


def stats(db):
    totals = {r["owner"]: r["n"] for r in db.execute("SELECT owner,COUNT(*) n FROM artifacts GROUP BY owner")}
    counters = {r["name"]: r["value"] for r in db.execute("SELECT * FROM counters")}
    usage = [dict(r) for r in db.execute("SELECT transport,COUNT(*) recorded_calls FROM usage GROUP BY transport")]
    return {"artifacts": sum(totals.values()), "owners": totals, "lookups": counters,
            "recorded_transport_usage": usage, "outbound_Onshape_calls_by_this_tool": 0,
            "usage_scope": "Manual operation log, not Onshape's authoritative annual counter"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("index")
    p.add_argument("paths", nargs="*", type=Path)
    p = commands.add_parser("lookup")
    p.add_argument("url")
    p.add_argument("--units", choices=("m", "mm", "in"), default="m")
    p = commands.add_parser("add")
    p.add_argument("file", type=Path)
    p.add_argument("--url", required=True)
    p.add_argument("--owner", required=True, choices=OWNERS)
    p.add_argument("--units", choices=("m", "mm", "in"), default="m")
    p.add_argument("--confirmed-response", action="store_true")
    p = commands.add_parser("search")
    p.add_argument("query")
    p.add_argument("--owner", choices=OWNERS)
    p.add_argument("--limit", type=int, default=20)
    p = commands.add_parser("context")
    p.add_argument("design", choices=OWNERS[:-1])
    p.add_argument("--out", type=Path)
    p = commands.add_parser("event")
    p.add_argument("file", type=Path)
    p = commands.add_parser("refreshed")
    p.add_argument("document_id")
    p.add_argument("microversion")
    p.add_argument("--confirmed-session-read", action="store_true")
    p = commands.add_parser("log-call")
    p.add_argument("--transport", required=True, choices=("onshape-session", "api-key", "private-oauth", "labs-featurescript-mcp", "webhook-notification"))
    p.add_argument("--status", type=int, required=True)
    p.add_argument("--note", default="")
    commands.add_parser("stats")
    args = parser.parse_args()
    with connect(args.db) as db:
        if args.command == "index":
            result = index_files(db, args.paths or [project.workspace_path(x) for x in project.read_registry().get("snapshot_dirs", ["receipts"])])
        elif args.command == "lookup":
            result = lookup(db, args.url, args.units)
        elif args.command == "add":
            result = add_response(db, args.file, args.url, args.owner, args.units, args.confirmed_response)
        elif args.command == "search":
            result = search(db, args.query, args.owner, min(max(args.limit, 1), 100))
        elif args.command == "context":
            result = context(db, args.design)
            if args.out:
                args.out.parent.mkdir(parents=True, exist_ok=True)
                args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        elif args.command == "event":
            result = ingest_event(db, read_json(args.file), project.read_registry())
        elif args.command == "refreshed":
            result = refresh_complete(db, args.document_id, args.microversion, args.confirmed_session_read)
        elif args.command == "log-call":
            db.execute("INSERT INTO usage(recorded_at,transport,status,note) VALUES (?,?,?,?)", (now(), args.transport, args.status, args.note))
            result = {"recorded": True}
        else:
            result = stats(db)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(2)
