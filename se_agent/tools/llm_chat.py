# rag_manager/tools/llm_chat.py
# Contract-compliant LLMChat tool with normalized ToolRegistry integration

from __future__ import annotations

from se_agent.core.tool_registry import BaseTool
from se_agent.mcp.artifact_registry import ArtifactRegistry, ArtifactPackage, Artifact
from se_agent.core.llm_config import load_llm_config
from se_agent.core.tool_registry import tool_registry  # fallback if agent doesn't inject registry
from openai import OpenAI
from typing import Any, Dict, List
from se_agent.core.tool_patterns  import  register_tool

@register_tool
class LLMChatTool(BaseTool):
    """
    Chat with an LLM. Tool-aware (reads ToolRegistry) and can persist conversation
    turns as 'conversation' artifacts based on tool-declared policy.
    """

    TOOL_NAME   = "llm_chat"
    DESCRIPTION = "CONDUCTS A TOOL-AWARE CHAT WITH THE LLM AND STORES CONVERSATION TURNS."
    CATEGORY    = "chat"

    # Artifact definition for stored turns
    ARTIFACTS = {
        "conversation": {
            "fields": {
                "prompt": {"type": "string"},
                "response": {"type": "string"},
                "model": {"type": "string"},
                "role": {"type": "string"},
            },
            "schema_version": "1.0",
            "description": "Single chat turn (user prompt + assistant response).",
        }
    }

    IO_SCHEMA = {
        "inputs": {
            "prompt": {
                "type": "string",
                "description": "User message to the assistant.",
                "required": False,  # messages[] may be provided instead
            },
            "context": {
                "type": "string",
                "description": "System prompt / tool awareness context.",
                "required": False,
            },
            "messages": {
                "type": "list",
                "description": "Optional full message list [{role,content}]. If absent, built from prompt+context.",
                "required": False,
            },
            "package": {
                "type": "string",
                "description": "Package to store conversation artifacts.",
                "required": False,
            },
            "config_name": {
                "type": "string",
                "description": "Optional LLM config block name to load.",
                "required": False,
            },
            # 🔹 NEW: allow callers (like Guided Session) to disable tool-awareness
            "tool_awareness": {
                "type": "bool",
                "description": (
                    "If false, do NOT inject tool-awareness or artifact-state hints. "
                    "Use this for Guided Session / no-tools mode."
                ),
                "required": False,
            },   
        },
        "outputs": {
            "conversation_artifact_id": {
                "type": "conversation",
                "remember": True,  # 🚩 tool author intent: keep turn in conversational memory
                "description": "Stored conversation turn artifact.",
            },
        },
    }

    def __init__(self, config_name: str | None = None):
        # Load LLM config (api_key, base_url, model)
        cfg = load_llm_config(config_name=config_name)
        self.client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
        self.model = cfg["model"]
        # The Agent injects its ToolRegistry instance; if not, we fallback to singleton
        self.tool_registry = None

    # --------- helpers ---------
    def _tool_awareness_block(self) -> str:
        """
        Build a compact tools summary from the (injected) registry or fallback.
        """
        registry = self.tool_registry or tool_registry
        tools_map = registry.list_tools()  # dict name -> meta dict
        lines: List[str] = []
        # Sort by name for determinism
        for name in sorted(tools_map.keys()):
            meta = tools_map[name] or {}
            desc = meta.get("description", "")
            lines.append(f"- {name}: {desc}")
        if not lines:
            return ""
        return (
            "You have access to the following tools:\n"
            + "\n".join(lines)
            + "\nRespond with JSON when proposing actions, e.g. "
              '{"actions":[{"tool":"read_leveled_csv","input":{"filename":"data.csv"}}]}'
        )

    def _rehydrate_messages_from_artifacts(
        self,
        artifacts: ArtifactRegistry | None,
        package_name: str | None,
        base_messages: List[Dict[str, str]],
        context_hint: str,
    ) -> List[Dict[str, str]]:
        """Pull recent conversation artifacts and append to messages."""
        msgs = list(base_messages or [])
        if artifacts and package_name:
            pkg: ArtifactPackage | None = artifacts.get_package(package_name)
            if pkg:
                convo = [a for a in pkg.artifacts.values() if a.type == "conversation"]
                # last few turns
                for a in convo[-5:]:
                    turn = a.content or {}
                    if "prompt" in turn:
                        msgs.append({"role": "user", "content": turn["prompt"]})
                    if "response" in turn:
                        msgs.append({"role": "assistant", "content": turn["response"]})
                if pkg.artifacts:
                    msgs.append({
                        "role": "system",
                        "content": (
                            context_hint
                            + "\n\n[State] Artifacts exist. Useful commands:\n"
                              "- list_artifacts {}\n"
                              "- show_artifact {\"type\":\"hierarchy\"}\n"
                              "- describe_state {}\n"
                        )
                    })
        return msgs

    # --------- run ---------
    def run(self, input_data: Dict[str, Any], artifacts: ArtifactRegistry | None = None,
            package_name: str | None = None, **kwargs) -> Dict[str, Any]:

        prompt  = (input_data or {}).get("prompt", "") or ""
        context = (input_data or {}).get("context", "") or ""
        messages: List[Dict[str, str]] = (input_data or {}).get("messages", []) or []
        pkg_from_input = (input_data or {}).get("package")
        cfg_name = (input_data or {}).get("config_name")

        # 🔹 NEW: tool-awareness flag (default True)
        tool_awareness: bool = (input_data or {}).get("tool_awareness", True)
        
        # If a config_name was provided at call time, refresh client/model
        if cfg_name:
            cfg = load_llm_config(config_name=cfg_name)
            self.client = OpenAI(api_key=cfg["api_key"], base_url=cfg["base_url"])
            self.model = cfg["model"]

        # Inject tool-awareness block
        tool_block = self._tool_awareness_block()
        if tool_block:
            context = (context + "\n\n" + tool_block).strip()

        # Rehydrate recent turns if no explicit messages provided
        target_package = pkg_from_input or package_name
        if not messages:
            messages = []
            if context:
                messages.append({"role": "system", "content": context})
            if prompt:
                messages.append({"role": "user", "content": prompt})
            # Add prior turns and state hint ONLY if tool-awareness is on
            if tool_awareness:
                messages = self._rehydrate_messages_from_artifacts(
                    artifacts, target_package, messages, "[Assistant Guidance]"
                )
        else:
            # Ensure system context is at the top
            if context:
                if messages[0].get("role") == "system":
                    messages[0] = {"role": "system", "content": context}
                else:
                    messages.insert(0, {"role": "system", "content": context})
            # Ensure the new prompt is included if not already present
            if prompt and (messages[-1].get("role") != "user" or messages[-1].get("content") != prompt):
                messages.append({"role": "user", "content": prompt})

        # ---- Call the LLM ----
        response = self.client.chat.completions.create(
            model=self.model,
            seed=42,            #  repeatability
            messages=messages
        )
        reply = response.choices[0].message.content

        # ---- Persist this turn as an artifact (and let runtime 'remember' policy apply) ----
        conversation_artifact_id = None
        if artifacts and target_package:
            pkg = artifacts.get_package(target_package)
            if pkg:
                art = Artifact(
                    type_="conversation",
                    content={"prompt": prompt, "response": reply, "model": self.model, "role": "assistant"},
                    metadata={"model": self.model}
                )
                saved = pkg.add_artifact(art)
                conversation_artifact_id = saved.id

        return {
            "message": "✅ Chat completed.",
            "response": reply,
            "model": self.model,
            "artifact_ids": {"conversation_artifact_id": conversation_artifact_id} if conversation_artifact_id else {}
        }

