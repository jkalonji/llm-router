"""
mcp_server/server.py
Expose le LLM Router via le protocole MCP (Model Context Protocol).

Deux transports :
- stdio (défaut) : pour Claude Code en local — lancé en sous-processus
- sse            : pour agents distants — écoute sur HTTP/SSE

Outils exposés :
- route_prompt      : classifie + recommande (mode chatbot/LLM)
- execute_prompt    : classifie + exécute sur le bon modèle (mode agent)
- get_log_summary   : retourne un résumé agrégé des tokens et coûts

Usage :
    # Local (Claude Code)
    uv run --env-file .env python mcp_server/server.py

    # Distant (agent externe)
    uv run --env-file .env python mcp_server/server.py --transport sse --host 0.0.0.0 --port 8000
"""

import argparse
import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.server.sse import SseServerTransport
from mcp import types
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount, Route

from router import Router
from logger import RouterLogger


app = Server("llm-router")
_router: Router | None = None
_logger: RouterLogger | None = None


def get_router() -> Router:
    global _router
    if _router is None:
        _router = Router()
    return _router


def get_logger() -> RouterLogger:
    global _logger
    if _logger is None:
        _logger = RouterLogger()
    return _logger


@app.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="route_prompt",
            description=(
                "Analyse un prompt utilisateur et retourne un plan de routage : "
                "décompose en sous-tâches atomiques, identifie la catégorie et le modèle optimal "
                "pour chacune. Mode recommandation uniquement — n'exécute pas le prompt."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Le prompt utilisateur à router.",
                    }
                },
                "required": ["prompt"],
            },
        ),
        types.Tool(
            name="execute_prompt",
            description=(
                "Analyse un prompt utilisateur, le décompose en sous-tâches, "
                "et exécute chaque sous-tâche sur le modèle Groq optimal. "
                "Retourne les réponses de chaque sous-tâche. Mode agent uniquement."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Le prompt utilisateur à router et exécuter.",
                    }
                },
                "required": ["prompt"],
            },
        ),
        types.Tool(
            name="get_log_summary",
            description=(
                "Retourne un résumé agrégé des appels LLM : tokens consommés par tier, "
                "coûts estimés, distribution des appels. Utile pour valider les hypothèses du POC."
            ),
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    import asyncio
    try:
        router = get_router()
        logger = get_logger()

        if name == "route_prompt":
            prompt = arguments.get("prompt", "").strip()
            if not prompt:
                return [types.TextContent(type="text", text='{"error": "Le champ prompt est vide."}')]
            result = await asyncio.to_thread(router.route, prompt, "recommendation")
            return [types.TextContent(type="text", text=json.dumps(result.to_dict(), ensure_ascii=False, indent=2))]

        elif name == "execute_prompt":
            prompt = arguments.get("prompt", "").strip()
            if not prompt:
                return [types.TextContent(type="text", text='{"error": "Le champ prompt est vide."}')]
            result = await asyncio.to_thread(router.route, prompt, "execution")
            return [types.TextContent(type="text", text=json.dumps(result.to_dict(), ensure_ascii=False, indent=2))]

        elif name == "get_log_summary":
            summary = await asyncio.to_thread(logger.summarize)
            return [types.TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]

        else:
            return [types.TextContent(type="text", text=f'{{"error": "Outil inconnu : {name}"}}')]

    except Exception as e:
        error_payload = json.dumps({"error": str(e), "type": type(e).__name__}, ensure_ascii=False)
        return [types.TextContent(type="text", text=error_payload)]


def build_sse_app(host: str, port: int) -> Starlette:
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> Response:
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await app.run(streams[0], streams[1], app.create_initialization_options())
        return Response()

    return Starlette(routes=[
        Route("/sse", endpoint=handle_sse, methods=["GET"]),
        Mount("/messages/", app=sse.handle_post_message),
    ])


async def run_stdio():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM Router MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport à utiliser (défaut : stdio)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Hôte d'écoute en mode SSE (défaut : 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port d'écoute en mode SSE (défaut : 8000)")
    return parser.parse_args()


if __name__ == "__main__":
    import asyncio
    import uvicorn

    args = parse_args()

    if args.transport == "sse":
        print(f"LLM Router MCP — transport SSE sur http://{args.host}:{args.port}/sse", flush=True)
        starlette_app = build_sse_app(args.host, args.port)
        uvicorn.run(starlette_app, host=args.host, port=args.port)
    else:
        asyncio.run(run_stdio())
