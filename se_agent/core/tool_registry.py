# se_agent/core/tool_registry.py
# Unified, normalized Tool Registry with basic planning helpers.
# Stores ONLY metadata dicts (never raw classes) to keep Agent/UI code simple.

from typing import Dict, Any, Optional, Type, List, Tuple
from collections import defaultdict, deque
from abc import ABC, abstractmethod


class BaseTool(ABC):
    """Abstract base class for all tools."""
    TOOL_NAME: str = ""
    DESCRIPTION: str = ""
    CATEGORY: str = "general"
    ARTIFACTS: Dict[str, Any] = {}
    IO_SCHEMA: Dict[str, Any] = {}

    @abstractmethod
    def run(self, *args, **kwargs) -> Dict[str, Any]:
        """Execute the tool. Must return a dict with at least a 'message' and/or 'artifact_ids'."""
        raise NotImplementedError

class ToolRegistry:
    """
    Central registry for tool metadata.

    Each entry is stored as a dict:
      {
        "class": <tool class>,
        "description": str,
        "category": str,
        "artifacts": dict,   # optional, as declared by the tool
        "io_schema": dict,   # {"inputs": {...}, "outputs": {...}}
      }

    This registry ALSO exposes light planning helpers that derive
    consumes/produces relationships from io_schema at query time.
    """

    def __init__(self):
        # name -> meta dict (NEVER a raw class)
        self.tools: Dict[str, Dict[str, Any]] = {}

    # --------------------------
    # Registration & Accessors
    # --------------------------
    def register_tool(self, tool_cls: Type) -> Type:
        """
        Normalize and register a tool class into metadata dict form.
        Returns the class to support decorator usage.
        """
        name = getattr(tool_cls, "TOOL_NAME", tool_cls.__name__)
        meta = {
            "class": tool_cls,
            "description": getattr(tool_cls, "DESCRIPTION", ""),
            "category": getattr(tool_cls, "CATEGORY", "general"),
            "artifacts": getattr(tool_cls, "ARTIFACTS", {}),
            "io_schema": getattr(tool_cls, "IO_SCHEMA", {}),
        }
        self.tools[name] = meta
        return tool_cls

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        return self.tools.get(name)

    def get_tool_class(self, name: str) -> Optional[Type]:
        info = self.tools.get(name)
        return info.get("class") if info else None

    def list_tools(self) -> Dict[str, Dict[str, Any]]:
        """Return the full tool map (name -> metadata dict)."""
        return self.tools

    def describe_tool(self, name: str) -> str:
        """Human-readable summary of a tool."""
        info = self.tools.get(name)
        if not info:
            return f"❌ Tool '{name}' not found."
        desc = info.get("description", "")
        cat = info.get("category", "general")
        inputs = ", ".join(
            v.get("type", "")
            for v in info.get("io_schema", {}).get("inputs", {}).values()
            if isinstance(v, dict)
        )
        outputs = ", ".join(
            v.get("type", "")
            for v in info.get("io_schema", {}).get("outputs", {}).values()
            if isinstance(v, dict)
        )
        return f"{name} ({cat}) – {desc}\nConsumes: {inputs or '—'}\nProduces: {outputs or '—'}"

    # --------------------------
    # Legacy Normalization
    # --------------------------
    def normalize_legacy_entries(self) -> None:
        """
        If previous code placed raw classes in self.tools, re-register
        them so every entry becomes a normalized metadata dict.
        Safe to call multiple times.
        """
        items: List[Tuple[str, Any]] = list(self.tools.items())
        for name, entry in items:
            if isinstance(entry, dict):
                continue
            # entry is a class – normalize it
            self.register_tool(entry)

    # --------------------------
    # IO Maps & Planning
    # --------------------------
    def _build_maps(self) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
        """
        Build {artifact_type -> [tool_names]} for consumes and produces.
        Derived on demand from io_schema so it's never stale.
        """
        consumes: Dict[str, List[str]] = defaultdict(list)
        produces: Dict[str, List[str]] = defaultdict(list)

        for name, info in self.tools.items():
            io = info.get("io_schema", {})
            for spec in io.get("inputs", {}).values():
                if isinstance(spec, dict):
                    art = spec.get("type")
                    if art:
                        consumes[art].append(name)
            for spec in io.get("outputs", {}).values():
                if isinstance(spec, dict):
                    art = spec.get("type")
                    if art:
                        produces[art].append(name)

        return consumes, produces

    def suggest_next(self, artifact_type: str) -> List[str]:
        """Return tool names that can consume the given artifact type."""
        consumes, _ = self._build_maps()
        return consumes.get(artifact_type, [])

    def get_producers(self, artifact_type: str) -> List[str]:
        """Return tool names that produce the given artifact type."""
        _, produces = self._build_maps()
        return produces.get(artifact_type, [])

    def plan_path(self, start_type: str, goal_type: str) -> List[str]:
        """
        Simple BFS planner over artifact types.

        Returns a list of tool names that transform from start_type to goal_type,
        or [] if no path is found.

        We consider a directed bipartite-style expansion:
          artifact_type --(tool that consumes it)--> next_artifact_types (tool outputs)
        """
        if start_type == goal_type:
            return []

        consumes, produces = self._build_maps()

        # Build a mapping: tool_name -> list of output artifact types
        tool_outputs: Dict[str, List[str]] = {}
        for tool_name, info in self.tools.items():
            outs = []
            for spec in info.get("io_schema", {}).get("outputs", {}).values():
                if isinstance(spec, dict) and spec.get("type"):
                    outs.append(spec["type"])
            tool_outputs[tool_name] = outs

        visited_artifacts = set([start_type])
        queue = deque([(start_type, [])])  # (current_artifact_type, plan_so_far)

        while queue:
            current_type, plan = queue.popleft()

            # Which tools can consume current_type?
            for tool_name in consumes.get(current_type, []):
                # What does this tool produce?
                outs = tool_outputs.get(tool_name, [])
                for ot in outs:
                    if ot == goal_type:
                        return plan + [tool_name]
                    if ot not in visited_artifacts:
                        visited_artifacts.add(ot)
                        queue.append((ot, plan + [tool_name]))

        return []


# --------------------------
# Singleton instance
# --------------------------
tool_registry = ToolRegistry()


# --------------------------
# Decorator convenience
# --------------------------
def register_tool(cls: Type) -> Type:
    """
    Decorator to register a tool class into the global registry.
    """
    tool_registry.register_tool(cls)
    return cls

