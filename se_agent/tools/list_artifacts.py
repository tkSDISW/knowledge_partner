# ------------------------------
# se_agent/tools/list_artifacts.py  (updated IO_SCHEMA + Markdown/HTML summary)
# ------------------------------
from __future__ import annotations
from typing import Any, Dict, List, Optional, Tuple

from se_agent.core.tool_patterns import  register_tool, DisplayTool  # keep existing inheritance
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage  # adjust import if needed

__all__ = ["ListArtifactsTool"]

@register_tool
class ListArtifactsTool(DisplayTool):
    """
    Display: List artifacts in the active (or specified) package and render a concise Markdown/HTML summary.
    
    Inputs:
    - package_name: Optional[str] -> Package to list (defaults to active package in registry)
    - type:         Optional[str] -> Filter by artifact type
    - max_rows:     Optional[int] -> Limit rows shown in Markdown (default 50)

    Outputs:
    - artifacts: list[dict]       -> Artifacts (sorted desc by created_at/updated_at if available)
    - ui:        str              -> Markdown-formatted summary
    - html:      str              -> HTML version of the summary
    """
    TOOL_NAME = "list_artifacts"
    DESCRIPTION  = (
        "List artifacts in the active (or specified) package with a Markdown summary. "
        "Optional filters: type, max_rows."
    )
    CATEGORY = "display"
    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "package_name": {"type": "string", "required": False, "description": "Override the active package."},
            "type": {"type": "string", "required": False, "description": "Filter by artifact type."},
            "max_rows": {"type": "integer", "required": False, "description": "Limit rows shown in Markdown (default 50)."},
        },
        "outputs": {
            "artifacts": {"type": "list", "remember": False, "description": "Artifacts in the package (sorted)."},
            # ui/html handled by DisplayTool renderers
        },
    }
    name = TOOL_NAME
    description = DESCRIPTION    
    # Note: DisplayTool typically calls `run`. Keep a `run` method to align with newer tools.
    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry | ArtifactPackage, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        raw = input_data or {}

        # Resolve package
        pkg = (
            raw.get("package_name")
            or package_name
            or (getattr(artifacts, "active_package", None) if isinstance(artifacts, ArtifactRegistry) else None)
        )
        if not pkg:
            md = "❌ No active package. Set one or pass `package_name`."
            return {"message": md, "ui": md, "html": self._as_html(md), "displayed": False, "artifacts": []}

        type_filter: Optional[str] = raw.get("type")
        try:
            max_rows = int(raw.get("max_rows", 50))
        except Exception:
            max_rows = 50

        # Collect artifacts from either the registry or a package instance
        items: List[Dict[str, Any]] = []
        if isinstance(artifacts, ArtifactRegistry):
            # Expect registry to return a list of dicts (id/type/name/created_at/metadata/updated_at etc.)
            try:
                items = artifacts.list_artifacts(pkg, type_filter=type_filter) or []
            except TypeError:
                # Some registries may not accept the kw; fall back without filter
                items = artifacts.list_artifacts(pkg) or []
                if type_filter:
                    items = [a for a in items if (a.get("type") == type_filter)]
        elif isinstance(artifacts, ArtifactPackage):
            for a in artifacts.artifacts.values():
                if type_filter and getattr(a, "type", None) != type_filter:
                    continue
                items.append({
                    "id": getattr(a, "id", None),
                    "type": getattr(a, "type", None),
                    "name": getattr(a, "name", None),
                    "created_at": getattr(a, "_created_at", None) or getattr(a, "created_at", None),
                    "updated_at": getattr(a, "updated_at", None),
                    "metadata": getattr(a, "metadata", None),
                })
        else:
            items = []

        # Normalize + sort items by updated_at or created_at (desc)
        def _sort_key(x: Dict[str, Any]) -> Tuple[int, str]:
            ts = x.get("updated_at") or x.get("created_at")
            return (0, ts) if isinstance(ts, str) and ts else (1, "")
        items = list(items)
        items.sort(key=_sort_key, reverse=True)

        # Nothing to show
        if not items:
            md = f"📭 No artifacts found in '{pkg}'."
            return {"message": md, "ui": md, "html": self._as_html(md), "artifacts": [], "displayed": True}

        # Build Markdown similar to list_workspace's table style
        header = f"📋 {len(items)} artifact(s) in '{pkg}'"
        lines: List[str] = [header, ""]

        # Table
        lines.append("| name | type | created/updated | id |")
        lines.append("|---|---|---|---|")
        for a in items[:max_rows]:
            name = a.get("name") or "—"
            typ  = a.get("type") or "—"
            ts   = a.get("updated_at") or a.get("created_at") or "—"
            aid  = a.get("id") or "—"
            short_id = aid[:8] if isinstance(aid, str) and len(aid) >= 8 else aid
            lines.append(f"| `{name}` | `{typ}` | `{ts}` | `{short_id}` |")

        if len(items) > max_rows:
            lines.append(f"\n> … showing first {max_rows} of {len(items)} rows")

        # Filters footer
        filters: List[str] = []
        if type_filter:
            filters.append(f"type=`{type_filter}`")
        if max_rows != 50:
            filters.append(f"max_rows=`{max_rows}`")
        if filters:
            lines.append("")
            lines.append("_Filters: " + ", ".join(filters) + "_")

        md = "\n".join(lines)

        return {
            "message": header,
            "ui": md,
            "html": self._as_html(md),
            "artifacts": items,
            "displayed": False,
        }

    # Back-compat: some older code paths may still call `render`. Delegate to run.
    def render(self, input_data, artifacts, package_name=None):
        return self.run(input_data or {}, artifacts, package_name=package_name)

    @staticmethod
    def _as_html(md: str) -> str:
        # Simple Markdown-to-HTML-ish conversion for line breaks; callers can render Markdown natively.
        return "<div style='font-family:system-ui;line-height:1.35'>" + md.replace("\\n", "<br/>") + "</div>"
