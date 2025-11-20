# se_agent/core/agent.py (excerpt)

import importlib, pkgutil
import se_agent.tools as tools_pkg

# Singleton registries
from se_agent.core.tool_registry import tool_registry
from se_agent.mcp.artifact_registry import artifact_registry

# Optional MemorySaver support (no-op if unavailable)
try:
    from langgraph.checkpoint.memory import MemorySaver
except Exception:
    MemorySaver = None


class AgentCore:
    def __init__(self, memory_saver=None, **kwargs):
        # ✅ use the same singletons decorators register into
        self.tools = tool_registry
        self.artifacts = artifact_registry

        # ✅ keep your existing saver (or None)
        self.memory_saver = memory_saver

        # ✅ import all tool modules so @register_tool executes
        self._autoload_tools()


    def _autoload_tools(self):
        """Import every module in se_agent.tools so tool decorators run."""
        for m in pkgutil.iter_modules(tools_pkg.__path__):
            importlib.import_module(f"{tools_pkg.__name__}.{m.name}")
