"""
Layer 3 -- the only file that touches the Gemini SDK directly.

Uses `google-genai` (`from google import genai`), the SDK Google currently
maintains -- the spec's snippet uses the now-deprecated `google.generativeai`,
but the JSON-mode/response_schema contract this file relies on is the same:
a Pydantic model passed straight in as the schema, no hand-written JSON
schema needed.
"""
import asyncio
import logging
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel

load_dotenv()

log = logging.getLogger("gemini")

# "gemini-2.5-flash" (the spec's pinned model) has since been cut off from
# new API keys ("no longer available to new users"). Track the alias
# instead of a dated snapshot so this doesn't happen again mid-demo.
MODEL = "gemini-flash-latest"

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


async def call_gemini(
    prompt: str, response_model: type[BaseModel], temperature: float, timeout_s: float
) -> BaseModel | None:
    """None is the load-bearing return value here. Every call site treats it
    as an expected branch -- not an error -- and falls back to whatever
    deterministic result it already has. Gemini being slow, rate-limited,
    returning malformed JSON, or just down is not exceptional; it's Tuesday."""
    try:
        client = _get_client()
        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=MODEL,
                contents=prompt,
                config={
                    "temperature": temperature,
                    "response_mime_type": "application/json",
                    "response_schema": response_model,
                    # Neither call needs deep reasoning, just constrained
                    # extraction/rewriting -- "low" cut measured latency from
                    # a 3.6-11s spread down to a consistent 2-4s.
                    "thinking_config": types.ThinkingConfig(thinking_level="low"),
                },
            ),
            timeout=timeout_s,
        )
        return response_model.model_validate_json(response.text)
    except Exception as e:  # noqa: BLE001 -- intentionally broad, see docstring
        # str(TimeoutError()) is "" -- fall back to repr so a timeout doesn't
        # log as a silent blank line indistinguishable from "no error at all".
        detail = str(e) or repr(e)
        log.warning("gemini call failed (%s): %s", response_model.__name__, detail)
        return None
