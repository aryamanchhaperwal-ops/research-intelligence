import os
import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

@dataclass
class AIResponse:
    content: str
    metadata: Dict[str, Any] = None

class AIProvider(Protocol):
    def analyze(self, question: str, context: str) -> AIResponse: ...
    def find_sources(self, question: str) -> List[str]: ...
    def generate_findings(self, source_content: str, question: str) -> List[Dict[str, Any]]: ...

class DemoAIProvider:
    """A safe provider that always works without an API key."""
    def analyze(self, question: str, context: str) -> AIResponse:
        return AIResponse(
            content=f"DEMO ANALYSIS: Based on the provided context, the answer to '{question}' is a synthesized demonstration of AI capabilities.",
            metadata={"provider": "demo", "status": "mocked"}
        )

    def find_sources(self, question: str) -> List[str]:
        return ["https://example.com/demo-source-1", "https://example.com/demo-source-2"]

    def generate_findings(self, source_content: str, question: str) -> List[Dict[str, Any]]:
        return [{
            "title": "Demo Finding",
            "text": f"Extracted insight regarding '{question}' from source text.",
            "confidence": "low",
            "statement": "This is a demo-generated finding."
        }]

class OpenAICompatibleProvider:
    """Provider for OpenAI, OpenRouter, Ollama, etc."""
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def _call(self, messages: List[Dict[str, str]]) -> str:
        import urllib.request
        import json
        import base64

        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "temperature": 0.7
        }).encode("utf-8")
        
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            },
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except Exception as e:
            raise RuntimeError(f"AI Provider Error: {e}")

    def analyze(self, question: str, context: str) -> AIResponse:
        prompt = f"Context: {context}\n\nQuestion: {question}\n\nProvide a professional research analysis."
        content = self._call([{"role": "user", "content": prompt}])
        return AIResponse(content=content, metadata={"provider": "openai-compatible", "model": self.model})

    def find_sources(self, question: str) -> List[str]:
        prompt = f"Suggest 3-5 high-quality research URLs to answer: {question}. Return ONLY a JSON list of URLs."
        content = self._call([{"role": "user", "content": prompt}])
        try:
            return json.loads(content)
        except:
            return []

    def generate_findings(self, source_content: str, question: str) -> List[Dict[str, Any]]:
        prompt = f"Source: {source_content}\n\nResearch Question: {question}\n\nExtract 2-3 key research findings as a JSON list of objects with keys: title, text, confidence, statement."
        content = self._call([{"role": "user", "content": prompt}])
        try:
            return json.loads(content)
        except:
            return []

def get_ai_provider() -> AIProvider:
    api_key = os.getenv("AI_API_KEY")
    base_url = os.getenv("AI_BASE_URL")
    model = os.getenv("AI_MODEL", "gpt-3.5-turbo")
    
    if not api_key or not base_url:
        return DemoAIProvider()
    
    return OpenAICompatibleProvider(api_key, base_url, model)

ai_service = get_ai_provider()
