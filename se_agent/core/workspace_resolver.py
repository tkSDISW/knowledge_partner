# se_agent/core/workspace_resolver.py
from se_agent.tools.workspace_store import _pkg_name, _load_ws

def resolve_workspace_names(input_obj, artifacts, package_name):
    pkg = _pkg_name(artifacts, package_name)
    if not pkg:
        return input_obj
    _, ws = _load_ws(artifacts, pkg)
    ws_map = ws.get("artifacts", {})

    def resolve_str(s: str):
        if not isinstance(s, str):
            return s
        key = s.lstrip("@")
        meta = ws_map.get(key)
        if not meta:
            return s
        # Prefer artifact_id; many tools accept either id or name
        return meta.get("artifact_id") or key

    def walk(x):
        if isinstance(x, dict):  return {k: walk(v) for k, v in x.items()}
        if isinstance(x, list):  return [walk(v) for v in x]
        if isinstance(x, str):   return resolve_str(x)
        return x

    return walk(input_obj)
