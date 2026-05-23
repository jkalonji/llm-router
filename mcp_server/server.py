"""
mcp_server/server.py
Expose le LLM Router via le protocole MCP (Model Context Protocol).
Compatible Claude Desktop, Cursor, et tout agent MCP-ready.

Outils exposés :
- route_prompt      : classifie + recommande (mode chatbot/LLM)
- execute_prompt    : classifie + exécute sur le bon modèle (mode agent)
- get_log_summary   : retourne un résumé agrégé des tokens et coûts
"""

import json
import sys
import os
from pathlib import Path

# Ajouter le répertoire racine au path pour les imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types

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
    router = get_router()
    logger = get_logger()

    if name == "route_prompt":
        prompt = arguments.get("prompt", "").strip()
        if not prompt:
            return [types.TextContent(type="text", text='{"error": "Le champ prompt est vide."}')]
        result = router.route(prompt, mode="recommendation")
        return [types.TextContent(type="text", text=json.dumps(result.to_dict(), ensure_ascii=False, indent=2))]

    elif name == "execute_prompt":
        prompt = arguments.get("prompt", "").strip()
        if not prompt:
            return [types.TextContent(type="text", text='{"error": "Le champ prompt est vide."}')]
        result = router.route(prompt, mode="execution")
        return [types.TextContent(type="text", text=json.dumps(result.to_dict(), ensure_ascii=False, indent=2))]

    elif name == "get_log_summary":
        summary = logger.summarize()
        return [types.TextContent(type="text", text=json.dumps(summary, ensure_ascii=False, indent=2))]

    else:
        return [types.TextContent(type="text", text=f'{{"error": "Outil inconnu : {name}"}}')]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
