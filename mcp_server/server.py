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

from mcp.server.fastmcp import FastMCP

from router import Router
from logger import RouterLogger


mcp = FastMCP("llm-router")
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


@mcp.tool()
def route_prompt(prompt: str) -> str:
    """
    Analyse un prompt utilisateur et retourne un plan de routage JSON.
    Décompose en sous-tâches atomiques, identifie la catégorie et le modèle optimal pour chacune.
    Mode recommandation uniquement — n'exécute pas le prompt.
    """
    if not prompt.strip():
        return json.dumps({"error": "Le champ prompt est vide."})
    try:
        result = get_router().route(prompt, mode="recommendation")
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "type": type(e).__name__}, ensure_ascii=False)


@mcp.tool()
def execute_prompt(prompt: str) -> str:
    """
    Analyse un prompt utilisateur, le décompose en sous-tâches,
    et exécute chaque sous-tâche sur le modèle Groq optimal.
    Retourne les réponses complètes de chaque sous-tâche. Mode agent uniquement.
    """
    if not prompt.strip():
        return json.dumps({"error": "Le champ prompt est vide."})
    try:
        result = get_router().route(prompt, mode="execution")
        return json.dumps(result.to_dict(), ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "type": type(e).__name__}, ensure_ascii=False)


@mcp.tool()
def get_log_summary() -> str:
    """
    Retourne un résumé agrégé des appels LLM : tokens consommés par tier,
    coûts estimés, distribution des appels.
    """
    try:
        summary = get_logger().summarize()
        return json.dumps(summary, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e), "type": type(e).__name__}, ensure_ascii=False)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLM Router MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http", "sse"],
        default="stdio",
        help="Transport à utiliser (défaut : stdio)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Hôte d'écoute en mode SSE (défaut : 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port d'écoute en mode SSE (défaut : 8000)")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.transport == "http":
        import uvicorn
        print(f"LLM Router MCP — transport HTTP sur http://{args.host}:{args.port}/mcp", flush=True)
        uvicorn.run(mcp.streamable_http_app(), host=args.host, port=args.port)
    elif args.transport == "sse":
        import uvicorn
        print(f"LLM Router MCP — transport SSE (legacy) sur http://{args.host}:{args.port}/sse", flush=True)
        uvicorn.run(mcp.sse_app(), host=args.host, port=args.port)
    else:
        import asyncio
        asyncio.run(mcp.run_stdio_async())
