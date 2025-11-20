from pathlib import Path
import json
from datetime import datetime
import json, re, ast

WANTED_NAME = "My_Prompts_prompt_path"

def get_prompt_path_from_artifacts(artifacts, package_name=None):
    pkg = artifacts.get_package(package_name) if package_name else artifacts.get_active_package()
    if not pkg: return None

    def _candidate_path(a):
        c = getattr(a, "content", None)
        m = getattr(a, "metadata", {}) or {}
        if isinstance(c, str) and c.strip():
            return c.strip()
        if isinstance(c, dict):
            for k in ("directory_path", "path", "prompt_path"):
                v = c.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        if isinstance(m, dict):
            for k in ("directory_path", "path", "prompt_path"):
                v = m.get(k)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        return None

    # pass 1: type/name/metadata.name
    for a in pkg.artifacts.values():
        t = getattr(a, "type", "")
        n = (getattr(a, "name", "") or "").strip()
        mn = ((getattr(a, "metadata", {}) or {}).get("name", "") or "").strip()
        if t == "prompt_path" or n == WANTED_NAME or mn == WANTED_NAME:
            p = _candidate_path(a)
            if p:
                P = Path(p).expanduser()
                return P if P.exists() else None

    # pass 2: any artifact that carries a plausible path
    for a in pkg.artifacts.values():
        p = _candidate_path(a)
        if p:
            P = Path(p).expanduser()
            if P.exists():
                return P
    return None


def scan_prompt_dir_json(prompt_dir: Path):
    """
    Compatibility wrapper that forwards to se_agent.core.prompt_store.scan_prompt_dir_json.
    """
    from se_agent.core.prompt_store import scan_prompt_dir_json as _scan
    return _scan(prompt_dir)

import json, re, ast
from pathlib import Path
from datetime import datetime

def _file_mtime_iso(path: Path) -> str:
    try:
        return datetime.utcfromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds") + "Z"
    except Exception:
        return ""


