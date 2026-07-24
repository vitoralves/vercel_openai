import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parent.parent / ".env.local")

if not os.getenv("OPENAI_API_KEY") and os.getenv("OPEN_API_KEY"):
    os.environ["OPENAI_API_KEY"] = os.environ["OPEN_API_KEY"]

app = FastAPI()


@app.get("/api", response_class=PlainTextResponse)
def idea():
    client = OpenAI()
    prompt = [
        {"role": "user", "content": "Come up with a new business idea for AI Agents"}
    ]
    response = client.chat.completions.create(model="gpt-5-nano", messages=prompt)
    return response.choices[0].message.content or ""
