from pathlib import Path
import os
import sys

from dotenv import load_dotenv

root = Path(__file__).resolve().parent.parent
load_dotenv(root / ".env.local", override=True)
load_dotenv(root / ".env", override=False)

os.chdir(root)
os.execvp(
    sys.executable,
    [
        sys.executable,
        "-m",
        "uvicorn",
        "api.index:app",
        "--reload",
        "--host",
        "127.0.0.1",
        "--port",
        "8000",
    ],
)
