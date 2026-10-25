import os
import httpx
from typing import List, Optional, Dict
from app.core.config import settings
from app.services.glossary_manager import GlossaryManager


class Translator:
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None, api_key: Optional[str] = None, glossary_name: Optional[str] = None, base_url: Optional[str] = None):
        self.provider = provider or settings.translation_provider
        self.model = model or settings.translation_model
        self.api_key = api_key or settings.translation_api_key
        self.base_url = base_url or settings.translation_base_url
        self.glossary_manager = GlossaryManager()
        self.glossary = self.glossary_manager.load_glossary(glossary_name) if glossary_name else {}
    
    async def translate_batch(self, texts: List[str], context: str = "") -> List[str]:
        if not texts:
            return []
        
        # Aplicar glossário antes da tradução
        texts_to_translate = []
        for t in texts:
            texts_to_translate.append(self.glossary_manager.apply_glossary(t, self.glossary))
        
        # Prompt para tradução PT-BR mantendo formatação/contexto
        system_prompt = """Você é um tradutor profissional especializado em tradução literária do inglês para português do Brasil.
Regras:
- Traduza com naturalidade, mantendo o tom e estilo originais
- Preserve nomes próprios, termos técnicos quando não houver tradução consagrada
- Mantenha expressões idiomáticas apropriadas ao PT-BR
- Não adicione explicações ou comentários
- Retorne APENAS o texto traduzido, um por linha na mesma ordem
- Preserve pontuação e estrutura quando possível"""

        user_prompt = f"Contexto: {context}\n\nTraduza os seguintes textos:\n\n" + "\n===SEPARATOR===\n".join(texts_to_translate)
        
        if self.provider == "openai":
            result = await self._translate_openai(system_prompt, user_prompt, texts_to_translate)
        elif self.provider == "ollama":
            result = await self._translate_ollama(system_prompt, user_prompt, texts_to_translate)
        elif self.provider == "gemini":
            result = await self._translate_gemini(system_prompt, user_prompt, texts_to_translate)
        else:
            result = texts_to_translate
        
        # Aplicar glossário pós-tradução também
        final_result = []
        for r in result:
            final_result.append(self.glossary_manager.apply_glossary(r, self.glossary))
        
        return final_result
    
    async def _translate_openai(self, system_prompt: str, user_prompt: str, texts: List[str]) -> List[str]:
        if not self.api_key:
            return texts
        
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url or None)
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
            )
            content = response.choices[0].message.content
            # Split by separator
            translated = content.split("\n===SEPARATOR===\n")
            if len(translated) == len(texts):
                return [t.strip() for t in translated]
            # Fallback: split by newlines
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            if len(lines) == len(texts):
                return lines
            return texts
        except Exception as e:
            print(f"OpenAI error: {e}")
            return texts
    
    async def _translate_ollama(self, system_prompt: str, user_prompt: str, texts: List[str]) -> List[str]:
        try:
            base_url = self.base_url or "http://ollama:11434"
            if base_url == "http://localhost:11434":
                base_url = "http://ollama:11434"
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "stream": False,
                        "options": {"temperature": 0.3}
                    }
                )
                content = response.json()["message"]["content"]
                translated = content.split("\n===SEPARATOR===\n")
                if len(translated) == len(texts):
                    return [t.strip() for t in translated]
                lines = [l.strip() for l in content.split("\n") if l.strip()]
                if len(lines) == len(texts):
                    return lines
                return texts
        except Exception as e:
            print(f"Ollama error: {e}")
            return texts
    
    async def _translate_gemini(self, system_prompt: str, user_prompt: str, texts: List[str]) -> List[str]:
        if not self.api_key:
            return texts
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model)
            prompt = f"{system_prompt}\n\n{user_prompt}"
            response = model.generate_content(prompt)
            content = response.text
            translated = content.split("\n===SEPARATOR===\n")
            if len(translated) == len(texts):
                return [t.strip() for t in translated]
            lines = [l.strip() for l in content.split("\n") if l.strip()]
            if len(lines) == len(texts):
                return lines
            return texts
        except Exception as e:
            print(f"Gemini error: {e}")
            return texts
