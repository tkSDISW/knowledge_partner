# rag_manager/tools/interactive_chat.py
# Contract-compliant InteractiveChat tool

from se_agent.core.tool_registry import BaseTool  # moved from tool_registry to base_tool
from se_agent.core.tool_patterns import  register_tool

@register_tool
class InteractiveChatTool(BaseTool):
    """
    Launch an interactive chat UI (delegates to AgentCore.interactive_chat()).
    This tool doesn't create artifacts directly; it's a UX/control entry point.
    """

    TOOL_NAME   = "interactive_chat"
    DESCRIPTION = "LAUNCHES AN INTERACTIVE CHAT SESSION; USES LLM_CHAT INTERNALLY."
    CATEGORY    = "control"

    # No artifacts produced; define IO for clarity
    ARTIFACTS: dict = {}

    IO_SCHEMA = {
        "inputs": {
            "context": {
                "type": "string",
                "description": "System context/instructions for the assistant.",
                "required": False,
            },
            "package": {
                "type": "string",
                "description": "Optional package in which to capture conversation artifacts.",
                "required": False,
            },
        },
        "outputs": {
            # No artifact outputs; this launches a UI/session
        },
    }

    def run(self, input_data: dict, artifacts=None, package_name: str | None = None, **kwargs):
        """
        Start an interactive chat UI.

        input_data:
          - context: system context for the assistant
          - package: optional package to capture conversation artifacts

        kwargs:
          - agent: AgentCore (required)
        """
        # Lazy import to avoid circulars
        from se_agent.core.agent import AgentCore

        context = (input_data or {}).get("context", "You are a helpful assistant.")
        pkg_from_input = (input_data or {}).get("package")

        # The current agent instance must be passed via kwargs
        agent: AgentCore = kwargs.get("agent")
        if not agent:
            raise ValueError("InteractiveChatTool requires 'agent' passed via kwargs")

        # Prefer explicit input package; fall back to package_name arg
        target_package = pkg_from_input or package_name

        # Delegate to AgentCore's UI launcher
        result = agent.interactive_chat(package_name=target_package, context=context)
        # Return a simple, contract-compliant response
        return {
            "message": "✅ Interactive chat launched.",
            "result": result  # whatever AgentCore returns (UI handle, URL, etc.)
        }
