import os
from moonlight import Provider

LLM_PROVIDER = Provider(
    source=os.getenv("LLM_SOURCE", ""),
    api=os.getenv("LLM_API_KEY", ""),
)

LLM_MODEL: str = os.getenv("LLM_MODEL", "")