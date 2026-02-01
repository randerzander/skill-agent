import json
import os
import time
from typing import Optional, Tuple

from openai import OpenAI

HOME = os.path.expanduser("~")
OAUTH_FILE = os.path.join(HOME, ".qwen", "oauth_creds.json")


def _load_oauth_token() -> str:
    with open(OAUTH_FILE, "r", encoding="utf-8") as f:
        creds = json.load(f)

    access_token = creds["access_token"]
    expiry_ms = creds.get("expiry_date")

    if expiry_ms and time.time() * 1000 > expiry_ms:
        raise RuntimeError(
            "Qwen OAuth token appears expired. Run `qwen` once to refresh it, then retry."
        )

    return access_token


def qwen_chat(
    prompt: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    temperature: float = 0.2,
) -> Tuple[str, Optional[dict]]:
    access_token = _load_oauth_token()
    resolved_base_url = base_url or os.getenv("OPENAI_BASE_URL", "https://portal.qwen.ai/v1")
    resolved_model = model or os.getenv("OPENAI_MODEL", "qwen3-coder-plus")

    client = OpenAI(
        api_key=access_token,
        base_url=resolved_base_url,
    )

    completion = client.chat.completions.create(
        model=resolved_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )

    message = completion.choices[0].message.content
    usage = completion.usage.model_dump() if getattr(completion, "usage", None) else None
    return message, usage
