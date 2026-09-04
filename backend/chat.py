"""
OpenRouter LLM integration with SSE streaming.
Tries each model in sequence and falls back on rate-limit or error.
"""

import json
import logging
from typing import AsyncGenerator

import httpx

from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a real estate assistant exclusively for DarGlobal and Wasalt property listings.

STRICT SCOPE RULES — you must follow these without exception:
1. Only answer questions about real estate: properties, prices, locations, amenities, \
buying, renting, investing, or comparing listings.
2. Answer factual questions (prices, sizes, specs) using ONLY the property data provided \
in the context. Never invent or estimate figures that are not in the context.
3. If the context does not contain enough information to answer, say so clearly and \
suggest the user refine their search.
4. If a question is not related to real estate or these listings, respond with exactly: \
"I can only help with real estate questions about DarGlobal and Wasalt listings."
5. Never write code, essays, poems, travel itineraries, or anything unrelated to property.

For every property you mention:
- State the source (DarGlobal or Wasalt)
- Include the price with its currency
- Provide the listing URL

Keep responses concise, factual, and professional.\
"""


def _build_messages(user_message: str, history: list[dict], context: str) -> list[dict]:
    """Assemble the messages array for the chat completion request."""
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Include the last 6 history turns to stay within context limits
    for turn in history[-6:]:
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({
        "role": "user",
        "content": f"Available properties:\n{context}\n\nQuestion: {user_message}",
    })
    return messages


async def stream_chat(
    message: str,
    history: list[dict],
    context: str,
    model_override: str | None = None,
) -> AsyncGenerator[str, None]:
    """
    Stream a chat response as SSE tokens.
    Yields: "data: {json}\\n\\n" for each token, then "data: [DONE]\\n\\n".
    """
    if not settings.openrouter_api_key:
        yield _sse({"error": "OPENROUTER_API_KEY is not configured"})
        return

    messages = _build_messages(message, history, context)
    models = [model_override] if model_override else settings.llm_models

    for model in models:
        success = False
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                async with client.stream(
                    "POST",
                    f"{settings.openrouter_base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.openrouter_api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": settings.app_url,
                        "X-Title": settings.app_title,
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": True,
                        "max_tokens": 1024,
                        "temperature": 0.3,
                    },
                ) as response:
                    if response.status_code == 429:
                        logger.warning("Rate limited on %s, trying next model", model)
                        continue
                    if response.status_code != 200:
                        body = await response.aread()
                        logger.warning("Model %s returned %d: %s", model, response.status_code, body[:200])
                        continue

                    logger.info("Streaming with model: %s", model)
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[5:].strip()
                        if data == "[DONE]":
                            yield "data: [DONE]\n\n"
                            return
                        try:
                            token = json.loads(data)["choices"][0]["delta"].get("content")
                            if token:
                                yield _sse({"token": token})
                        except (json.JSONDecodeError, KeyError, IndexError):
                            continue
                    success = True

        except httpx.TimeoutException:
            logger.warning("Timeout on model %s, trying next", model)
        except Exception:
            logger.exception("Unexpected error with model %s", model)

        if success:
            return

    yield _sse({"error": "All models failed or rate limited. Please try again."})
    yield "data: [DONE]\n\n"


def _sse(payload: dict) -> str:
    return "data: " + json.dumps(payload) + "\n\n"
