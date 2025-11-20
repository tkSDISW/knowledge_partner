from __future__ import annotations
from pathlib import Path
from datetime import datetime, timezone
import json

SCHEMA_VERSION = 1

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def validate_prompt_spec(spec: dict) -> tuple[bool, str | None]:
    if not isinstance(spec, dict):
        return False, "Spec must be a JSON object."
    if "template" not in spec or not isinstance(spec["template"], str) or not spec["template"].strip():
        return False, "Missing or invalid 'template' (string required)."
    if "vars" not in spec or not isinstance(spec["vars"], list) or not all(isinstance(v, str) for v in spec["vars"]):
        return False, "Missing or invalid 'vars' (list of strings required)."
    if "defaults" in spec and not isinstance(spec["defaults"], dict):
        return False, "'defaults' must be an object (name->value)."
    if "tags" in spec and (not isinstance(spec["tags"], list) or not all(isinstance(t, str) for t in spec["tags"])):
        return False, "'tags' must be a list of strings."
    return True, None

def load_prompt_json(path: Path) -> dict:
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"error": f"Invalid JSON in {path.name}: {e}"}
    ok, err = validate_prompt_spec(spec)
    if not ok:
        return {"error": f"{path.name}: {err}"}
    # normalize
    return {
        "name": spec.get("title") or path.stem,
        "type": "prompt_json",
        "text": spec["template"],
        "vars": list(spec["vars"]),
        "defaults": dict(spec.get("defaults") or {}),
        "tags": list(spec.get("tags") or []),
        "updated_at": spec.get("updated_at") or _now_iso(),
        "source_path": str(path),
        "version": spec.get("version", SCHEMA_VERSION),
    }

def scan_prompt_dir_json(prompt_dir: Path) -> list[dict]:
    rows: list[dict] = []
    if not prompt_dir or not prompt_dir.exists():
        return rows
    for p in sorted(prompt_dir.glob("*.json")):
        info = load_prompt_json(p)
        if "error" in info:
            # still include it so the pane can show the error inline
            rows.append({
                "name": p.stem, "type": "prompt_json",
                "text": "", "vars": [], "defaults": {},
                "tags": [], "updated_at": "", "source_path": str(p),
                "error": info["error"], "version": None,
            })
        else:
            rows.append(info)
    # newest first by updated_at
    rows.sort(key=lambda r: r.get("updated_at",""), reverse=True)
    return rows

def write_prompt_json(path: Path, spec: dict) -> tuple[bool, str | None]:
    ok, err = validate_prompt_spec(spec)
    if not ok:
        return False, err
    if "version" not in spec:
        spec["version"] = SCHEMA_VERSION
    if "updated_at" not in spec:
        spec["updated_at"] = _now_iso()
    try:
        path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return True, None
    except Exception as e:
        return False, str(e)



