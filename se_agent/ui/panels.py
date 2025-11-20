# se_agent/ui/panels.py
from IPython.display import display, Markdown
from datetime import datetime
from se_agent.core.prompt_store import scan_prompt_dir_json
# --- prompt helpers ---------------------------------------------------------

def _collect_prompt_artifacts(artifacts, package_name, prompt_dir=None):
    pkg = artifacts.get_package(package_name) if package_name else artifacts.get_active_package()
    rows = []

    """# in-memory prompt artifacts (unchanged)
    if pkg:
        for a in pkg.artifacts.values():
            t = getattr(a, "type", "")
            if t not in {"prompt", "prompt_template"}:
                continue
            name = getattr(a, "name", None) or getattr(a, "id", "")[:8]
            meta = getattr(a, "metadata", {}) or {}
            content = getattr(a, "content", None)
            text = content if t == "prompt" else (content or {}).get("template", "")
            rows.append({
                "name": name, "type": t,
                "updated_at": meta.get("updated_at") or meta.get("created_at") or meta.get("timestamp") or "",
                "text": str(text or ""), "tags": meta.get("tags") or [],
                "vars": (content or {}).get("vars") if isinstance(content, dict) else [],
                "defaults": (content or {}).get("defaults") if isinstance(content, dict) else {},
            })
    """
    # directory .json prompts (authoritative)
    if prompt_dir:
        rows.extend(scan_prompt_dir_json(prompt_dir))

    rows.sort(key=lambda r: r.get("updated_at",""), reverse=True)
    return rows

def _filter_prompts(rows, query: str):
    q = (query or "").strip().lower()
    if not q: return rows
    out = []
    for r in rows:
        hay = " ".join([
            r.get("name",""),
            r.get("text",""),
            " ".join(r.get("tags") or [])
        ]).lower()
        if q in hay:
            out.append(r)
    return out

def _ts(rec):
    for k in ("updated_at", "created_at", "timestamp"):
        v = rec.get(k)
        if isinstance(v, (int, float)): return float(v)
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
    return 0.0

def _mk_table(rows, cols, title, empty_msg="*(none)*"):
    display(Markdown(f"**{title}**"))
    if not rows:
        display(Markdown(empty_msg)); return
    head = "| " + " | ".join(cols) + " |\n"
    sep  = "| " + " | ".join(["---"]*len(cols)) + " |\n"
    body = "".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n" for r in rows)
    display(Markdown(head + sep + body))

def _collect_workspace(artifacts, package_name):
    pkg = artifacts.get_package(package_name) if package_name else artifacts.get_active_package()
    if not pkg: return []
    ws = next((a for a in pkg.artifacts.values() if getattr(a, "type", "") == "workspace"), None)
    if not ws: return []
    mem = (ws.content or {}).get("memory", {})
    rows = [{"name": k, "type": (v.get("type") or "value"), "updated_at": v.get("updated_at", "")} for k, v in mem.items()]
    rows.sort(key=_ts, reverse=True)
    return rows

def _collect_artifacts(artifacts, package_name):
    pkg = artifacts.get_package(package_name) if package_name else artifacts.get_active_package()
    if not pkg: return []
    rows = []
    for a in pkg.artifacts.values():
        t = getattr(a, "type", "")
        if t in {"workspace", "conversation"}:  # hide internals
            continue
        nm = getattr(a, "name", None) or getattr(a, "id", None) or "—"
        md = getattr(a, "metadata", {}) or {}
        rows.append({
            "name": nm,
            "type": t or "—",
            "updated_at": md.get("updated_at") or md.get("created_at") or md.get("timestamp") or ""
        })
    rows.sort(key=_ts, reverse=True)
    return rows

def _relevant_tools(ToolRegistry, work_rows, art_rows):
    # conservative, simple heuristic for now
    names = set([r["name"] for r in work_rows + art_rows if r.get("name")])
    types = set([r["type"] for r in work_rows + art_rows if r.get("type")])
    tools = []
    for name, cls in getattr(ToolRegistry, "_tools", {}).items():
        io = getattr(cls, "IO_SCHEMA", {}) or {}
        inputs = io.get("inputs", {}) if isinstance(io, dict) else {}

        # if tool references names/types, or has no required inputs -> show
        req = [k for k, spec in inputs.items() if isinstance(spec, dict) and spec.get("required")]
        if ("name" in inputs or "id" in inputs) and names:
            tools.append(name); continue
        desc_blob = " ".join(str((spec or {}).get("description") or "") for spec in inputs.values())
        if any(t.lower() in desc_blob.lower() for t in types if t):
            tools.append(name); continue
        if not req:
            tools.append(name); continue
    return sorted(set(tools), key=str.lower)

# se_agent/ui/panels.py
from IPython.display import display, Markdown
from datetime import datetime

def _ts(rec):
    for k in ("updated_at", "created_at", "timestamp"):
        v = rec.get(k)
        if isinstance(v, (int, float)): 
            return float(v)
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
            except Exception:
                pass
    return 0.0

def _mk_table(rows, cols, title, empty_msg="*(none)*"):
    display(Markdown(f"**{title}**"))
    if not rows:
        display(Markdown(empty_msg)); 
        return
    head = "| " + " | ".join(cols) + " |\n"
    sep  = "| " + " | ".join(["---"]*len(cols)) + " |\n"
    body = "".join("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |\n" for r in rows)
    display(Markdown(head + sep + body))

def _collect_workspace(artifacts, package_name):
    pkg = artifacts.get_package(package_name) if package_name else artifacts.get_active_package()
    if not pkg: 
        return []
    ws = next((a for a in pkg.artifacts.values() if getattr(a, "type", "") == "workspace"), None)
    if not ws: 
        return []
    mem = (ws.content or {}).get("memory", {})
    rows = [{"name": k, "type": (v.get("type") or "value"), "updated_at": v.get("updated_at", "")} for k, v in mem.items()]
    rows.sort(key=_ts, reverse=True)
    return rows

def _collect_artifacts(artifacts, package_name):
    pkg = artifacts.get_package(package_name) if package_name else artifacts.get_active_package()
    if not pkg: 
        return []
    rows = []
    for a in pkg.artifacts.values():
        t = getattr(a, "type", "")
        if t in {"workspace", "conversation"}:   # hide internals
            continue
        nm = getattr(a, "name", None) or getattr(a, "id", None) or "—"
        md = getattr(a, "metadata", {}) or {}
        rows.append({
            "name": nm,
            "type": t or "—",
            "updated_at": md.get("updated_at") or md.get("created_at") or md.get("timestamp") or ""
        })
    rows.sort(key=_ts, reverse=True)
    return rows

def _relevant_tools(tool_registry_like, work_rows, art_rows):
    """
    Conservative relevance: show tools that mention names/types in inputs,
    or have no required inputs. Works with either a ._tools dict (name->class)
    or .tools dict (name->meta with 'class').
    """
    names = set([r["name"] for r in work_rows + art_rows if r.get("name")])
    types = set([r["type"] for r in work_rows + art_rows if r.get("type")])

    # normalize iteration over registered tools
    items = []
    if hasattr(tool_registry_like, "_tools"):
        items = list(getattr(tool_registry_like, "_tools").items())  # name -> class
        def get_cls(meta_or_cls): return meta_or_cls
    else:
        items = list(getattr(tool_registry_like, "tools", {}).items())  # name -> meta
        def get_cls(meta_or_cls): 
            return (meta_or_cls or {}).get("class")

    tools = []
    for name, meta in items:
        cls = get_cls(meta)
        if not cls:
            continue
        io = getattr(cls, "IO_SCHEMA", {}) or {}
        inputs = io.get("inputs", {}) if isinstance(io, dict) else {}

        req = [k for k, spec in inputs.items() if isinstance(spec, dict) and spec.get("required")]
        if ("name" in inputs or "id" in inputs) and names:
            tools.append(name); 
            continue
        desc_blob = " ".join(str((spec or {}).get("description") or "") for spec in inputs.values())
        if any(t.lower() in desc_blob.lower() for t in types if t):
            tools.append(name); 
            continue
        if not req:
            tools.append(name); 
            continue

    return sorted(set(tools), key=str.lower)

