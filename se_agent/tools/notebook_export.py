# se_agent/tools/notebook_export.py
# Minimal, contract-compliant BaseTool that exports the agent's history
# to a Jupyter notebook for replay. No artifact inputs/outputs.

from __future__ import annotations
from typing import Any, Dict

from se_agent.core.tool_patterns import register_tool,BaseTool   # <-- decorator forwards to tool_registry
from se_agent.core.notebook_exporter import NotebookExporter


@register_tool
class NotebookExportTool(BaseTool):
    """
    Export the agent's interaction history as a Jupyter notebook (.ipynb)
    suitable for replay or sharing. This tool is "display/control" only:
    it does not consume or produce artifacts.
    """

    # ---- Standard tool metadata ------------------------------------------------
    TOOL_NAME   = "notebook_export"
    DESCRIPTION = "EXPORT AGENT HISTORY AS A JUPYTER NOTEBOOK FOR REPLAY."
    CATEGORY    = "control"

    # No new artifact types declared by this tool
    ARTIFACTS: Dict[str, Any] = {}

    # Declare inputs/outputs for consistency (no artifact I/O here)
    IO_SCHEMA = {
        "inputs": {
            "filename": {
                "type": "string",
                "required": False,
                "description": "Output .ipynb filename (default: agent_replay.ipynb).",
            },
        },
        "outputs": {
            # No artifact outputs; returns a dict with path info
        },
    }

    # ---- Contract-compliant run signature --------------------------------------
    def run(self, input_data: Dict[str, Any], artifacts=None, package_name: str | None = None, **kwargs) -> Dict[str, Any]:
        """
        input_data:
          - filename (str, optional): output notebook filename
        kwargs:
          - agent (AgentCore, required): the live agent instance whose history is exported
        """
        agent = kwargs.get("agent")
        if not agent:
            raise ValueError("NotebookExportTool requires the 'agent' instance via kwargs (agent=agent).")

        filename = (input_data or {}).get("filename", "agent_replay.ipynb")
        exporter = NotebookExporter(agent)
        out_path = exporter.export(filename=filename)

        msg = f"✅ Notebook exported: {out_path}"
        return {"message": msg, "path": str(out_path)}
