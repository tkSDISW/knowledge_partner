# ------------------------------
# se_agent/tools/_workspace_store.py
# ------------------------------
from __future__ import annotations
from datetime import datetime
from typing import Tuple, Dict, Any

WORKSPACE_ARTIFACT_NAME = "_workspace_store"
WORKSPACE_ARTIFACT_TYPE = "workspace"


def _pkg_name(artifacts, package_name: str | None) -> str | None:
    return package_name or getattr(artifacts, "active_package", None)


def _load_ws(artifacts, pkg: str | None) -> Tuple[Any, Dict[str, Any]]:
    if not pkg:
        raise ValueError("No active package for workspace store")
    try:
        pkg_obj = artifacts.get_package(pkg)
        for a in pkg_obj.artifacts.values():
            if getattr(a, "type", None) == WORKSPACE_ARTIFACT_TYPE and getattr(a, "name", None) == WORKSPACE_ARTIFACT_NAME:
                content = (getattr(a, "content", {}) or {})
                content.setdefault("artifacts", {})
                content.setdefault("memory", {})   # free-form workspace memory entries
                content.setdefault("injections_once", {})  # map of name->digest for one-shot prompt injects
                return a, content
    except Exception:
        pass
    # create fresh store
    content = {"artifacts": {}, "memory": {}, "injections_once": {}}
    meta = {"ui_summary": "Workspace store", "name": WORKSPACE_ARTIFACT_NAME}
    a = artifacts.add_artifact(pkg, WORKSPACE_ARTIFACT_TYPE, content, meta)
    return a, content


def _save_ws(artifacts, pkg: str, art, content: Dict[str, Any]) -> None:
    art.content = content
    if hasattr(artifacts, "update_artifact"):
        artifacts.update_artifact(pkg, art.id, art)


def _now_iso() -> str:
    from datetime import datetime
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"

