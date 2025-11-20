# ------------------------------
# se_agent/tools/list_workspace.py  (updated to produce Markdown UI/HTML)
# ------------------------------
from __future__ import annotations
from typing import Any, Dict, Optional, List, Tuple

from se_agent.core.tool_patterns import register_tool, DisplayTool
from se_agent.mcp.artifact_registry import ArtifactRegistry
from .workspace_store import _pkg_name, _load_ws

__all__ = ["ListWorkspaceTool"]


@register_tool
class ListWorkspaceTool(DisplayTool):
    """
    Display: List the artifacts and memory entries currently registered in the active workspace store,
    and render a concise Markdown/HTML summary suitable for chat display.

    Inputs:
    - section: Optional[str]  -> 'artifacts' or 'memory' to filter the output section
    - type:    Optional[str]  -> Filter by 'type' inside artifacts/memory
    - max_rows: Optional[int] -> Truncate the per-section listing to this many rows (default 20)

    Outputs:
    - artifacts: list[dict]   -> Workspace artifacts (sorted desc by updated_at)
    - memory:    list[dict]   -> Workspace memory entries (sorted desc by updated_at)
    - ui:        str          -> Markdown-formatted summary
    - html:      str          -> HTML version of the summary
    """

    TOOL_NAME = "list_workspace"
    DESCRIPTION = "DISPLAYS THE CURRENT WORKSPACE CONTENTS: ARTIFACTS AND MEMORY ENTRIES (with Markdown summary)."
    CATEGORY = "display"

    ARTIFACTS: Dict[str, Any] = {}

    IO_SCHEMA: Dict[str, Any] = {
        "inputs": {
            "section": {"type": "string", "required": False, "description": "Optional: 'artifacts' or 'memory' to filter."},
            "type":    {"type": "string", "required": False, "description": "Optional: filter by artifact or memory 'type'."},
            "max_rows": {"type": "integer", "required": False, "description": "Optional: limit rows shown per section (default 20)."},
        },
        "outputs": {
            "artifacts": {"type": "list", "remember": False, "description": "Workspace artifacts (sorted by updated_at desc)."},
            "memory":    {"type": "list", "remember": False, "description": "Workspace memory entries (sorted by updated_at desc)."},
            # 'ui' and 'html' are displayed by DisplayTool, not stored as artifacts
        }
    }

    name = TOOL_NAME
    description = DESCRIPTION

    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry, package_name: Optional[str] = None, **_: Any) -> Dict[str, Any]:
        raw = input_data or {}
        pkg = _pkg_name(artifacts, package_name)
        if not pkg:
            md = "❌ No active package."
            return {"message": md, "ui": md, "html": self._as_html(md), "displayed": False, "artifacts": [], "memory": []}

        section_filter: Optional[str] = raw.get("section")
        type_filter: Optional[str] = raw.get("type")
        try:
            max_rows = int(raw.get("max_rows", 20))
        except Exception:
            max_rows = 20

        _, ws = _load_ws(artifacts, pkg)
        entries = ws.get("artifacts", {}) or {}
        mem     = ws.get("memory", {}) or {}

        def _sorted_items(d: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
            items: List[Dict[str, Any]] = []
            for name, meta in d.items():
                row = {
                    "name": name,
                    "type": meta.get("type"),
                    "updated_at": meta.get("updated_at"),
                }
                if "artifact_id" in meta:
                    row["artifact_id"] = meta.get("artifact_id")
                items.append(row)

            # Sort by updated_at desc (missing last)
            def _key(x: Dict[str, Any]) -> Tuple[int, str]:
                t = x.get("updated_at")
                return (0, t) if isinstance(t, str) and t else (1, "")
            items.sort(key=_key, reverse=True)
            return items

        items_art = _sorted_items(entries)
        items_mem = _sorted_items(mem)

        # Apply optional filters
        if type_filter:
            items_art = [x for x in items_art if (x.get("type") == type_filter)]
            items_mem = [x for x in items_mem if (x.get("type") == type_filter)]
        if section_filter == "artifacts":
            items_mem = []
        elif section_filter == "memory":
            items_art = []

        # Build Markdown similar in spirit to show_artifact_memory.py
        header = f"⚙️ Workspace (Working Memory) for '{pkg}'"
        lines: List[str] = [header, ""]

        def _render_table(title: str, rows: List[Dict[str, Any]]) -> List[str]:
            if not rows:
                return [f"**{title}:** _none_"]
            out: List[str] = [f"**{title}:** {len(rows)} item(s)"]
            # Table header
            out.append("")
            out.append("| name | type | updated_at | id |")
            out.append("|---|---|---|---|")
            for r in rows[:max_rows]:
                name = r.get("name") or "—"
                typ  = r.get("type") or "—"
                upd  = r.get("updated_at") or "—"
                aid  = (r.get("artifact_id") or "—")
                # shorten id if it looks UUID-ish
                if isinstance(aid, str) and len(aid) >= 8:
                    short = aid[:8]
                else:
                    short = aid
                out.append(f"| `{name}` | `{typ}` | `{upd}` | `{short}` |")
            # Show truncation note if needed
            if len(rows) > max_rows:
                out.append(f"\n> … showing first {max_rows} of {len(rows)} rows")
            return out

        # Compose sections
        if items_art:
            lines += _render_table("Artifacts", items_art)
            lines.append("")
        else:
            lines.append("**Artifacts:** _none_")
            lines.append("")

        if items_mem:
            lines += _render_table("Memory", items_mem)
            lines.append("")
        else:
            lines.append("**Memory:** _none_")
            lines.append("")

        # Small footer with active filters
        filters: List[str] = []
        if section_filter:
            filters.append(f"section=`{section_filter}`")
        if type_filter:
            filters.append(f"type=`{type_filter}`")
        if max_rows != 20:
            filters.append(f"max_rows=`{max_rows}`")
        if filters:
            lines.append("_Filters: " + ", ".join(filters) + "_")

        md = "\n".join(lines)

        return {
            "message": header,
            "ui": md,
            "html": self._as_html(md),
            "artifacts": items_art,
            "memory": items_mem,
        }

    @staticmethod
    def _as_html(md: str) -> str:
        # Simple Markdown-to-HTML-ish conversion for line breaks; callers can render Markdown natively.
        return "<div style='font-family:system-ui;line-height:1.35'>" + md.replace("\\n", "<br/>") + "</div>"

