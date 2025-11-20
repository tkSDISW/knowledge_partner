# rag_manager/tools/summarizer.py

from se_agent.core.tool_registry import BaseTool


class SummarizerTool(BaseTool):
    name = "summarizer"
    description = "Summarize input text into concise form."

    def run(self, input_data, artifacts=None, **kwargs):
        text = str(input_data)
        # 🚨 Placeholder logic: Replace with LLM call later
        summary = text[:75] + "..." if len(text) > 75 else text
        return {"summary": summary}
