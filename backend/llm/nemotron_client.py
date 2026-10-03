"""
Nemotron / LLM Client Compatibility Layer for ScholarScout.
Wraps the unified AIClient to provide backward compatibility
for existing modules while offering new robust features.
"""

from typing import Dict, Any, Optional, TypeVar, Type
from pydantic import BaseModel
from backend.llm.client import ai_client, AIClient
from backend.llm.schemas import LLMResult
from backend.logging_utils import logger

T = TypeVar("T", bound=BaseModel)

class NemotronClient:
    """Compatibility facade delegating to the unified AIClient."""
    def __init__(self):
        self._client = ai_client

    def is_configured(self) -> bool:
        return self._client.is_configured()

    def get_client(self):
        return self._client.get_client()

    async def test_connection(self) -> Dict[str, Any]:
        return await self._client.test_connection()

    async def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.1,
        job_id: Optional[int] = None,
        schema: Optional[Type[T]] = None
    ) -> Optional[Any]:
        """
        Generates JSON. If schema is provided, returns validated Pydantic model instance.
        If schema is not provided, uses a generic dict parse.
        """
        if not self.is_configured():
            return None

        try:
            if schema:
                result = await self._client.generate_structured(
                    schema=schema,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    temperature=temperature,
                    job_id=job_id
                )
                return result.data
            else:
                # Direct JSON generation
                res = await self._client.generate_text(
                    system_prompt=system_prompt + "\nRespond with valid JSON.",
                    user_prompt=user_prompt,
                    temperature=temperature,
                    job_id=job_id
                )
                import json
                cleaned = self._client._extract_json_string(res.raw_text)
                return json.loads(cleaned)
        except Exception as e:
            logger.warning(f"[NemotronClient] generate_json error: {e}")
            return None

    async def generate_text(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        job_id: Optional[int] = None
    ) -> Optional[str]:
        if not self.is_configured():
            return None
        try:
            res = await self._client.generate_text(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                job_id=job_id
            )
            return res.data
        except Exception as e:
            logger.warning(f"[NemotronClient] generate_text error: {e}")
            return None

nemotron_client = NemotronClient()
