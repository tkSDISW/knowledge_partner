# se_agent/tools/show_memory.py
# Contract-compliant "show_memory" (package summary)

from __future__ import annotations
from collections import defaultdict
from typing import Any, Dict, List


from se_agent.core.tool_patterns import register_tool  ,DisplayTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage


@register_tool
class ShowArtifactMemoryTool(DisplayTool):
    """
    Summarize the current package memory: artifact counts by type and example names.
    Optional inputs: package (str), type_filter (str), max_names (int, default 8).
    """

    TOOL_NAME   = "show_artifact_memory"
    DESCRIPTION = "SUMMARIZE ARTIFACTS IN A PACKAGE WITH COUNTS AND EXAMPLES. Optional inputs: package_name (str), type_filter (str), max_names (int, default 8)."
    CATEGORY    = "display"

    # This tool doesn't create artifacts; declare IO only for agent planning
    ARTIFACTS: Dict[str, Any] = {}

    IO_SCHEMA = {
        "inputs": {
            "package":     {"type": "string", "required": False, "description": "Package to inspect (defaults to agent package)."},
            "type_filter": {"type": "string", "required": False, "description": "Only include artifacts of this type."},
            "max_names":   {"type": "integer", "required": False, "description": "Max example names per type (default 8)."},
        },
        "outputs": {
            # no artifact outputs; returns a structured dict with 'ui'/'html'
        },
    }

    def run(self, input_data, artifacts: ArtifactRegistry, package_name=None, **kwargs):
        raw = input_data or {}
        pkg_name   = raw.get("package") or package_name
        type_filter = raw.get("type_filter")
        try:
            max_names = int(raw.get("max_names", 8))
        except Exception:
            max_names = 8

        if not pkg_name:
            md = "⚠️ No active package; pass `package` or use agent.use_package(...)."
            return {"message": md, "ui": md, "html": self._as_html(md), "summary": [], "total": 0}

        # Resolve package & items
        pkg: ArtifactPackage | None = artifacts.get_package(pkg_name)
        if not pkg or not getattr(pkg, "artifacts", None):
            md = f"📭 No artifacts found in '{pkg_name}'."
            return {"message": md, "ui": md, "html": self._as_html(md), "summary": [], "total": 0}

        # Collect minimal rows
        items: List[Dict[str, Any]] = []
        for a in pkg.artifacts.values():
            if type_filter and a.type != type_filter:
                continue
            items.append({
                "id": a.id,
                "type": a.type,
                "name": getattr(a, "name", None),
                "created_at": getattr(a, "_created_at", None),
                "metadata": a.metadata or {},
            })

        if not items:
            md = f"📭 No artifacts of type '{type_filter}' in '{pkg_name}'."
            return {"message": md, "ui": md, "html": self._as_html(md), "summary": [], "total": 0}

        # Group by type
        groups = defaultdict(list)
        for row in items:
            groups[row.get("type") or "unknown"].append(row)

        # Build Markdown
        header = f"Show Artifact 📋 summary for '{pkg_name}'"
        lines = [header, ""]
        total = 0
        summary = []
        for t, rows in sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0] or "")):
            count = len(rows); total += count
            sample = [(r.get("name") or f"(id:{r['id'][:8]})") for r in rows[:max_names]]
            extra = f" +{count-max_names}" if count > max_names else ""
            lines.append(f"- `{t or 'unknown'}`: **{count}**" + (f"  (e.g., {', '.join(sample)}{extra})" if sample else ""))
            summary.append({
                "type": t, "count": count,
                "examples": [{"id": r["id"], "name": r.get("name")} for r in rows[:max_names]],
                "all_ids": [r["id"] for r in rows],
            })
        lines.append(""); lines.append(f"**Total:** {total}")

        md = "\n".join(lines)
        return {"message": header, 
                "ui": md, 
                "html": self._as_html(md),
                "summary": summary, 
                "total": total}

    @staticmethod
    def _as_html(md: str) -> str:
        return "<div style='font-family:system-ui;line-height:1.35'>" + md.replace("\n", "<br/>") + "</div>"
