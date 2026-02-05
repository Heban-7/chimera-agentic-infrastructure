"""
Project Chimera — LLM Client (OpenRouter Integration)

Provides a unified async interface to LLM providers via the OpenAI-compatible
API exposed by OpenRouter. This allows swapping models without changing
application code.

Spec References:
    - specs/technical.md: §8 (Technology Stack)
    - research/architecture_strategy.md: §The Planner (Gemini 3 Pro),
      §The Worker (Gemini 3 Flash)
    - .cursor/rules/project-chimera.mdc: Rule 3 (Async-first)
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("chimera.orchestrator.llm_client")


class LLMClient:
    """
    Async LLM client using the OpenAI-compatible API (OpenRouter).

    Spec Ref: specs/technical.md §8, project-chimera.mdc Rule 3

    This client is the single point of contact for all LLM inference
    in the Chimera system. Both Planner (reasoning) and Worker (execution)
    use this client with different system prompts.

    Usage:
        client = LLMClient()
        response = await client.generate(
            system_prompt="You are a content strategist...",
            user_prompt="Create a tweet about Ethiopian fashion",
        )
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 60.0,
    ):
        self.api_key = api_key or os.getenv("LLM_API_KEY", "")
        self.base_url = base_url or os.getenv(
            "LLM_API_BASE_URL", "https://openrouter.ai/api/v1"
        )
        self.model = model or os.getenv(
            "LLM_MODEL", "arcee-ai/trinity-large-preview:free"
        )
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/aiqem/chimera",
                "X-Title": "Project Chimera",
            },
            timeout=httpx.Timeout(timeout),
        )

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        response_format: str | None = None,
    ) -> dict[str, Any]:
        """
        Generate a response from the LLM.

        Args:
            system_prompt: System-level instructions (persona, constraints).
            user_prompt: The actual task or question.
            temperature: Creativity control (0.0 = deterministic, 1.0 = creative).
            max_tokens: Maximum response length.
            response_format: If "json", instruct the model to return valid JSON.

        Returns:
            Dict with 'content' (str), 'model' (str), 'usage' (dict),
            'latency_ms' (int).
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if response_format == "json":
            # Instruct the model to return JSON
            messages[0]["content"] += "\n\nIMPORTANT: Respond ONLY with valid JSON. No markdown, no explanation."

        start_time = time.monotonic()

        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            elapsed_ms = int((time.monotonic() - start_time) * 1000)

            content = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})

            logger.info(
                "LLM response received in %dms (model: %s, tokens: %s)",
                elapsed_ms,
                self.model,
                usage.get("total_tokens", "?"),
            )

            return {
                "content": content,
                "model": data.get("model", self.model),
                "usage": usage,
                "latency_ms": elapsed_ms,
            }

        except httpx.HTTPStatusError as e:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            logger.error(
                "LLM API error (%d) after %dms: %s",
                e.response.status_code,
                elapsed_ms,
                e.response.text[:200],
            )
            raise
        except Exception as e:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            logger.error("LLM request failed after %dms: %s", elapsed_ms, str(e))
            raise

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> dict[str, Any] | list:
        """
        Generate a structured JSON response from the LLM.

        Uses lower temperature for more deterministic structured output.
        Parses the response and returns the Python object.

        Returns:
            Parsed JSON (dict or list).

        Raises:
            json.JSONDecodeError: If the model fails to return valid JSON.
        """
        result = await self.generate(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format="json",
        )

        content = result["content"].strip()

        # Strip markdown code fences if the model wraps JSON in them
        if content.startswith("```"):
            lines = content.split("\n")
            # Remove first line (```json) and last line (```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            content = "\n".join(lines).strip()

        try:
            parsed = json.loads(content)
            return parsed
        except json.JSONDecodeError:
            logger.warning("LLM returned invalid JSON, attempting to extract...")
            # Try to find JSON within the response
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
            start = content.find("[")
            end = content.rfind("]") + 1
            if start >= 0 and end > start:
                return json.loads(content[start:end])
            raise

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
