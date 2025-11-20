# rag_manager/tools/wordcount.py

from se_agent.core.tool_registry import BaseTool


class WordCountTool(BaseTool):
    name = "wordcount"
    description = "Count the number of words in input text or artifact."

    def run(self, input_data, artifacts=None, **kwargs):
        # Prefer explicit input
        text = str(input_data) if input_data else ""

        # If no explicit input, fall back to artifacts (first one)
        if not text and artifacts:
            first_artifact = next(iter(artifacts.values()))
            text = str(first_artifact.content)

        words = text.split()
        count = len(words)
        return {"word_count": count, "sample": " ".join(words[:10])}
