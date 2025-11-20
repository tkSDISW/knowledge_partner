import nbformat as nbf

class NotebookExporter:
    def __init__(self, agent):
        self.agent = agent

    def _replace_ids_with_names(self, record):
        """Return a copy of record with artifact IDs replaced by namees when available."""
        rec = dict(record)  # shallow copy
        input_data = dict(rec.get("input") or {})

        # If referencing artifacts by id
        if "id" in input_data:
            pkg = self.agent.artifacts.get_package(rec["package"]) if rec.get("package") else None
            if pkg:
                art = pkg.artifacts.get(input_data["id"])
                if art and art.name:
                    # Prefer name in replay
                    input_data.pop("id")
                    input_data["name"] = art.name

        rec["input"] = input_data
        return rec

    def export(self, filename="agent_replay.ipynb", minimal=True):
        history = self.agent.get_history()
        nb = nbf.v4.new_notebook()
        cells = []

        # Header
        cells.append(
            nbf.v4.new_markdown_cell("# Agent Replay Notebook\nGenerated from agent history.")
        )

        for i, record in enumerate(history):
            tool = record["tool"]

            # Skip interactive-only steps
            if tool in {"interactive_chat", "notebook_export"}:
                continue

            safe_record = self._replace_ids_with_names(record)

            # Markdown description
            md = f"### Step {i+1}: Run `{tool}`"
            if safe_record.get("input"):
                if minimal and tool == "llm_chat":
                    md += f"\nPrompt: `{safe_record['input'].get('prompt', '')}`"
                else:
                    md += f"\nInput: `{safe_record['input']}`"
            cells.append(nbf.v4.new_markdown_cell(md))

            # Code cell
            if minimal and tool == "llm_chat":
                code = (
                    f"agent.run('llm_chat', input_data={{'prompt': "
                    f"'{safe_record['input'].get('prompt', '')}'}})"
                )
            else:
                code = (
                    f"_ = agent.run('{tool}', input_data={safe_record.get('input') or {}})"
                )
            cells.append(nbf.v4.new_code_cell(code))

        nb["cells"] = cells
        with open(filename, "w") as f:
            nbf.write(nb, f)

        return {"message": f"📓 Notebook exported to {filename}", "filename": filename}
