"""Create (or update) the Vapi tools and assistant for this project.

Usage (after the API is deployed):
    set VAPI_API_KEY=...            (Vapi dashboard -> API Keys -> Private key)
    set SERVER_URL=https://your-app.onrender.com
    python scripts/setup_vapi.py

Optional:
    VAPI_MODEL=gpt-4o               (any OpenAI model Vapi offers)
    VAPI_ASSISTANT_ID=...           (update an existing assistant instead of creating one)

Uses only the Python standard library, so it runs without extra installs.
API shapes follow docs.vapi.ai (POST /tool, POST /assistant, PATCH /assistant/{id}).
"""
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.vapi.ai"

FIRST_MESSAGE = (
    "Hi, thanks for calling! This is Riley with new patient registration. "
    "I can get you set up in just a few minutes. Could I start with your first and last name?"
)


def call(method: str, path: str, key: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0 (patient-intake-setup)"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        print(f"\nVapi returned {exc.code} for {method} {path}:\n{exc.read().decode()}")
        sys.exit(1)


def load_prompt() -> str:
    text = (ROOT / "prompts" / "system_prompt.md").read_text(encoding="utf-8")
    # Strip reviewer-only design notes.
    return "\n".join(line for line in text.splitlines() if not line.startswith("## NOTE:")).strip()


def main() -> None:
    key = os.getenv("VAPI_API_KEY")
    server = os.getenv("SERVER_URL", "").rstrip("/")
    if not key or not server.startswith("https://"):
        sys.exit("Set VAPI_API_KEY and SERVER_URL (https://...) first.")
    webhook = f"{server}/vapi/webhook"
    model = os.getenv("VAPI_MODEL", "gpt-4o")

    tools = json.loads((ROOT / "vapi" / "tools.json").read_text(encoding="utf-8"))
    tool_ids = []
    for tool in tools:
        tool["server"] = {"url": webhook}
        created = call("POST", "/tool", key, tool)
        tool_ids.append(created["id"])
        print(f"tool {tool['function']['name']}: {created['id']}")

    assistant = {
        "name": "Riley - Patient Intake",
        "firstMessage": FIRST_MESSAGE,
        "model": {
            "provider": "openai",
            "model": model,
            "messages": [{"role": "system", "content": load_prompt()}],
            "toolIds": tool_ids,
            "tools": [{"type": "endCall"}],
        },
        # End-of-call reports (transcripts) are sent here.
        "server": {"url": webhook},
    }
    existing = os.getenv("VAPI_ASSISTANT_ID")
    if existing:
        result = call("PATCH", f"/assistant/{existing}", key, assistant)
        print(f"\nUpdated assistant {result['id']}")
    else:
        result = call("POST", "/assistant", key, assistant)
        print(f"\nCreated assistant {result['id']}")
    print(
        "\nNext: Vapi dashboard -> Phone Numbers -> Create Phone Number -> Free Vapi Number,\n"
        "then open the number and choose 'Riley - Patient Intake' under Inbound Settings, and Save."
    )


if __name__ == "__main__":
    main()
