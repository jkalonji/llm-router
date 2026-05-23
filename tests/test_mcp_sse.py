"""
Test direct des outils MCP via transport SSE.
Lance le serveur SSE en parallèle, appelle route_prompt et execute_prompt,
affiche les résultats et les erreurs éventuelles.

Usage : uv run --env-file .env python tests/test_mcp_sse.py
"""
import asyncio
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp import ClientSession
from mcp.client.sse import sse_client


SERVER_URL = "http://localhost:8090/sse"


async def call_tool(session: ClientSession, tool_name: str, arguments: dict) -> str:
    result = await session.call_tool(tool_name, arguments)
    return result.content[0].text if result.content else "(vide)"


async def main():
    print(f"Connexion à {SERVER_URL} ...", flush=True)
    try:
        async with sse_client(SERVER_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                print(f"Outils disponibles : {[t.name for t in tools.tools]}\n")

                print("--- route_prompt ---")
                r1 = await call_tool(session, "route_prompt", {"prompt": "Traduis 'bonjour' en anglais"})
                print(json.dumps(json.loads(r1), indent=2, ensure_ascii=False))

                print("\n--- execute_prompt ---")
                r2 = await call_tool(session, "execute_prompt", {"prompt": "Reformate en JSON : nom=Alice, age=30"})
                print(json.dumps(json.loads(r2), indent=2, ensure_ascii=False))

                print("\n--- get_log_summary ---")
                r3 = await call_tool(session, "get_log_summary", {})
                print(json.dumps(json.loads(r3), indent=2, ensure_ascii=False))

    except Exception as e:
        print(f"ERREUR : {type(e).__name__}: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
