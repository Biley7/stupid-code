"""Check that the REST API and the real MCP server report the same Study Mode value.

Run from the workspace root:
    LLM_PROVIDER=mock .venv/bin/python scripts/check_study_mode_parity.py

The script analyzes a tiny temporary repository through the API, toggles Study Mode
through the API, then reads ``study_mode_enabled`` through the API (vitals) and through
the MCP server launched in a subprocess exactly like ``.kiro/settings/mcp.json``.
Exit code 0 means both surfaces succeeded and agreed for every checked value.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import asyncio
import json
import os
import tempfile
from typing import Any

EXPECTED_TOOLS = {
    "dissect_symbol",
    "trace_blast_radius",
    "analyze_folder_architecture",
    "check_spec_drift",
    "get_comprehension_vitals",
}

_FILES = {
    "util.py": "def helper(x):\n    return x + 1\n",
    "app.py": "from util import helper\n\n\ndef run(n):\n    return helper(n)\n",
}


def compare(label: str, api: object, mcp: object) -> bool:
    """Print both values and return True when both are booleans and equal."""
    print(f"[{label}] API study_mode_enabled={api}")
    print(f"[{label}] MCP study_mode_enabled={mcp}")
    ok = isinstance(api, bool) and isinstance(mcp, bool) and api == mcp
    if not ok:
        print(f"[{label}] MISMATCH: API returned {api!r}, MCP returned {mcp!r}")
    return ok


def _tool_payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structured_content", None)
    if isinstance(structured, dict):
        return structured
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
    return {}


async def _mcp_study_mode(repo: str, db: str) -> bool | str:
    """Read the value through the real server; return an error description on failure."""
    from mcp import Client, StdioServerParameters

    env = {**os.environ, "LLM_PROVIDER": "mock", "STUPID_CODE_DB_PATH": db}
    params = StdioServerParameters(
        command=".venv/bin/python",
        args=["backend/mcp_server/server.py"],
        env=env,
        cwd=str(ROOT),
    )
    async with Client(params) as client:
        names = {tool.name for tool in (await client.list_tools()).tools}
        if names != EXPECTED_TOOLS:
            return f"unexpected tool list {sorted(names)}"
        payload = _tool_payload(
            await client.call_tool("get_comprehension_vitals", {"repo_path": repo})
        )
    if payload.get("ok") is not True:
        return f"error {payload.get('error')!r}"
    return payload["vitals"]["study_mode_enabled"]  # type: ignore[no-any-return]


def main() -> int:
    os.environ["LLM_PROVIDER"] = "mock"
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "repo"
        repo.mkdir()
        for name, text in _FILES.items():
            (repo / name).write_text(text, encoding="utf-8")
        db = str(Path(tmp) / "parity.db")
        os.environ["STUPID_CODE_DB_PATH"] = db

        from fastapi.testclient import TestClient

        from backend.api.main import create_app
        from backend.api.services import Services
        from backend.engines.cache_store import CacheStore
        from backend.engines.llm_router import LLMRouter

        services = Services.build(CacheStore(), LLMRouter())
        client = TestClient(create_app(services=services))

        ingest = client.post("/api/repos/ingest", json={"path": str(repo)})
        if ingest.status_code != 200:
            print(f"API ingest failed: {ingest.status_code} {ingest.json()}")
            return 1
        repo_id = ingest.json()["repo_id"]

        all_ok = True
        for enabled in (True, False):
            toggled = client.post(
                f"/api/repos/{repo_id}/study-mode", json={"enabled": enabled}
            )
            if toggled.status_code != 200:
                print(f"API study-mode failed: {toggled.status_code} {toggled.json()}")
                return 1
            vitals = client.get(f"/api/repos/{repo_id}/vitals")
            if vitals.status_code != 200:
                print(f"API vitals failed: {vitals.status_code} {vitals.json()}")
                return 1
            api_value = vitals.json()["study_mode_enabled"]
            mcp_value = asyncio.run(_mcp_study_mode(str(repo), db))
            all_ok &= compare(f"set {enabled}", api_value, mcp_value)
            all_ok &= api_value is enabled
        print("PARITY OK" if all_ok else "PARITY FAILED")
        return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
