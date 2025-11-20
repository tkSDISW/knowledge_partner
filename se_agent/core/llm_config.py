# rag_manager/core/llm_config.py
import os, json
from pathlib import Path

def load_llm_config(config_name=None, model=None, api_key=None, base_url=None):
    """
    Load LLM configuration from ~/.secrets/model_configs.json or environment variables.
    
    Priority order:
      1. Explicit args
      2. Named config in model_configs.json
      3. Default config (_default) in model_configs.json
      4. Environment variables (OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL)
    """

    cfg_path = Path.home() / ".secrets" / "model_configs.json"
    config = {}

    if cfg_path.exists():
        try:
            with cfg_path.open() as f:
                all_cfg = json.load(f)
            if config_name:
                config = all_cfg.get(config_name, {})
            elif "_default" in all_cfg:
                config = all_cfg.get(all_cfg["_default"], {})
        except Exception as e:
            print(f"⚠️ Could not load config from {cfg_path}: {e}")

    return {
        "api_key": api_key or config.get("api_key") or os.getenv("OPENAI_API_KEY"),
        "base_url": base_url or config.get("base_url") or os.getenv("OPENAI_BASE_URL"),
        "model": model or config.get("model") or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    }
