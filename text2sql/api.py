"""Façade OpenAI locale : authentification, borne d'entrée et une question à la fois.

Ne démarre aucun LLM. Le streaming SSE transporte la réponse après son calcul ;
ce n'est pas un streaming des étapes internes ou des tokens du modèle.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import math
import re
import time
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .agent import answer
from .config import Settings


class Message(BaseModel):
    role: str
    content: str = Field(max_length=16000)


class ChatRequest(BaseModel):
    model: str
    messages: list[Message] = Field(min_length=1, max_length=16)
    stream: bool = False


class RerankRequest(BaseModel):
    model: str
    query: dict[str, str]
    passages: list[dict[str, str]] = Field(max_length=128)


def create_app(responder=None, settings=None):
    settings = settings or Settings.load()
    responder = responder or answer
    app = FastAPI(title="Calorvia Text-to-SQL", version="0.1.0")
    lock = asyncio.Lock()

    async def auth(authorization: str | None = Header(default=None)):
        if not settings.api_key:
            raise HTTPException(503, "T2SQL_API_KEY non configurée")
        if not authorization or not hmac.compare_digest(
            authorization, "Bearer " + settings.api_key
        ):
            raise HTTPException(
                401, "Clé API requise", headers={"WWW-Authenticate": "Bearer"}
            )

    @app.get("/health")
    async def health():
        return {"status": "api_running", "sources_checked": False, "llm_checked": False}

    @app.get("/v1/models", dependencies=[Depends(auth)])
    async def models():
        return {
            "object": "list",
            "data": [
                {
                    "id": "calorvia-agent",
                    "object": "model",
                    "created": 0,
                    "owned_by": "local",
                }
            ],
        }

    @app.post("/v1/reranking", dependencies=[Depends(auth)])
    async def cpu_rerank(body: RerankRequest):
        # Adaptateur CPU lexical au format NIM ; ce n'est PAS le BGE GPU.
        # Évite de charger une seconde copie du reranker dans un sous-processus.
        if body.model != "calorvia-cpu-lexical":
            raise HTTPException(
                400, "Cet endpoint fournit seulement calorvia-cpu-lexical"
            )
        texts = [body.query.get("text", "")] + [
            p.get("text", "") for p in body.passages
        ]
        if sum(map(len, texts)) > 500000:
            raise HTTPException(413, "Lot de reranking trop volumineux")

        def tokens(t):
            return set(re.findall(r"\w+", t.casefold()))

        q = tokens(texts[0])
        rankings = []
        for index, text in enumerate(texts[1:]):
            words = tokens(text)
            score = len(q & words) / math.sqrt(max(1, len(q) * len(words)))
            rankings.append({"index": index, "logit": score})
        return {
            "model": body.model,
            "rankings": sorted(rankings, key=lambda r: r["logit"], reverse=True),
        }

    @app.post("/v1/chat/completions", dependencies=[Depends(auth)])
    async def completions(body: ChatRequest):
        if body.model != "calorvia-agent":
            raise HTTPException(404, "Modèle inconnu")
        messages = [m.model_dump() for m in body.messages]
        if any(m["role"] not in {"user", "assistant", "system"} for m in messages):
            raise HTTPException(400, "Rôle non pris en charge")
        if messages[-1]["role"] != "user":
            raise HTTPException(
                400, "Le dernier message doit être une question utilisateur"
            )
        if sum(len(m["content"]) for m in messages) > 32000:
            raise HTTPException(413, "Conversation trop longue")
        try:
            async with lock:
                result = await responder(
                    messages[-1]["content"], history=messages[:-1], settings=settings
                )
        except ValueError as exc:
            raise HTTPException(503, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                503, "Un service local est indisponible ; consulter les journaux locaux"
            ) from exc
        identifier, created = "chatcmpl-" + uuid.uuid4().hex, int(time.time())
        content = result["answer"]
        if body.stream:

            async def events():
                for delta, finish in [
                    ({"role": "assistant"}, None),
                    ({"content": content}, None),
                    ({}, "stop"),
                ]:
                    yield (
                        "data: "
                        + json.dumps(
                            {
                                "id": identifier,
                                "object": "chat.completion.chunk",
                                "created": created,
                                "model": body.model,
                                "choices": [
                                    {
                                        "index": 0,
                                        "delta": delta,
                                        "finish_reason": finish,
                                    }
                                ],
                            },
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )
                yield "data: [DONE]\n\n"

            return StreamingResponse(events(), media_type="text/event-stream")
        return {
            "id": identifier,
            "object": "chat.completion",
            "created": created,
            "model": body.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop",
                }
            ],
        }

    return app


app = create_app()
