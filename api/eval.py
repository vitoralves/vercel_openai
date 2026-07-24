import json
import os
import re
from typing import Any

from openai import OpenAI

DEFAULT_MODEL = "gpt-5-nano"


def score_idea(content: str) -> dict[str, Any]:
    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    client = OpenAI()
    prompt = (
        "Score this business idea for the AI agent economy. "
        "Return ONLY valid JSON with keys: "
        "novelty (1-10 int), feasibility (1-10 int), overall (1-10 int), "
        "notes (string, 1-2 sentences).\n\n"
        f"IDEA:\n{content[:6000]}"
    )
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    text = (response.choices[0].message.content or "").strip()
    return _parse_scores(text)


def _parse_scores(text: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise ValueError("Model did not return JSON scores")
        data = json.loads(match.group(0))

    return {
        "novelty": int(data.get("novelty", 0)),
        "feasibility": int(data.get("feasibility", 0)),
        "overall": int(data.get("overall", 0)),
        "notes": str(data.get("notes", "")).strip(),
    }
