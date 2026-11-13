import re
from typing import List, Optional, Dict

import httpx

from app.core.config import settings
from app.services.glossary_manager import GlossaryManager


# Marcador numerado usado no prompt/resposta. É mais confiável que o separador
# antigo (`===SEPARATOR===`), que o modelo frequentemente ignorava ou fundia.
NUMBER_MARKER_PATTERN = re.compile(r"\[\[\s*(\d+)\s*\]\]")
LEGACY_SEPARATORS = ("\n===SEPARATOR===\n", "===SEPARATOR===")

# Limite de termos do glossário repetidos no prompt. Um glossário grande não
# pode inflar cada chamada, então só entram os termos presentes no lote.
MAX_PROMPT_TERMS = 40

# Erro irrecuperável da chamada ao provedor (rede, autenticação, etc.).
# Nesse caso não adianta subdividir o lote: todas as divisões falhariam igual.
class TranslationCallError(Exception):
    pass


def looks_untranslated(source: str, translated: str) -> bool:
    """Detecta respostas que apenas repetem o texto original.

    Só é aplicável a textos longos: nomes próprios e frases curtas podem
    legitimamente permanecer iguais.
    """
    if not translated or not translated.strip():
        return True
    if len(source) >= 40 and source.strip() == translated.strip():
        return True
    return False


class Translator:
    def __init__(self, provider: Optional[str] = None, model: Optional[str] = None, api_key: Optional[str] = None, glossary_name: Optional[str] = None, base_url: Optional[str] = None):
        self.provider = provider or settings.translation_provider
        self.model = model or settings.translation_model
        self.api_key = api_key or settings.translation_api_key
        self.base_url = base_url or settings.translation_base_url
        self.glossary_manager = GlossaryManager()
        self.glossary = self.glossary_manager.load_glossary(glossary_name) if glossary_name else {}
        # Falhas registradas durante a tradução (evita "sucesso falso")
        self.errors: List[str] = []
        self._max_errors = 200

    async def translate_batch(
        self, texts: List[str], context: str = ""
    ) -> List[Optional[str]]:
        if not texts:
            return []

        # Termos do glossário presentes neste lote entram no prompt como
        # instrução explícita. O texto original não é pré-substituído: trocar
        # termos no meio do inglês quebra a gramática da frase enviada
        # ("a dobra de fogo master"). A substituição pós-tradução continua
        # como rede de segurança para termos que o modelo deixar em inglês.
        terms = self._matching_terms(texts)

        results: List[Optional[str]] = [None] * len(texts)

        async def translate_indices(indices: List[int]) -> None:
            """Traduz um subconjunto de índices, subdividindo em caso de falha.

            Se a resposta do modelo não puder ser segmentada, o subconjunto é
            dividido pela metade e cada metade é tentada novamente. Assim uma
            falha de segmentação afeta no máximo o bloco que realmente falhou,
            em vez de descartar o lote inteiro (comportamento antigo).
            """
            subset = [texts[i] for i in indices]

            try:
                parsed = await self._translate_subset(subset, context, terms)
            except TranslationCallError:
                # Falha de infraestrutura: interrompe o job para que possa ser
                # retomado, em vez de marcar os blocos como "não traduzidos".
                raise

            pending: List[int] = []
            for index, translated in zip(indices, parsed):
                if not looks_untranslated(texts[index], translated):
                    results[index] = translated
                else:
                    pending.append(index)

            if not pending:
                return

            if len(indices) == 1:
                self._record_error(
                    f"{self.provider}: bloco não traduzido ({len(subset[0])} caracteres)"
                )
                return

            if len(pending) == 1:
                await translate_indices(pending)
                return

            middle = len(pending) // 2
            await translate_indices(pending[:middle])
            await translate_indices(pending[middle:])

        await translate_indices(list(range(len(texts))))

        # Aplicar glossário pós-tradução também.
        # Blocos sem tradução permanecem None para que a pipeline os marque
        # como falha (em vez de gravar o original como se fosse tradução).
        final_result: List[Optional[str]] = []
        for translated in results:
            if translated is None:
                final_result.append(None)
            else:
                final_result.append(
                    self.glossary_manager.apply_glossary(translated, self.glossary)
                )

        return final_result

    def _matching_terms(self, texts: List[str]) -> Dict[str, str]:
        """Termos do glossário que aparecem no lote.

        O glossário é aplicado por substituição textual, o que não cobre
        flexões nem muda a concordância. Repetir os termos no prompt faz o
        modelo usá-los com naturalidade.
        """
        if not self.glossary:
            return {}

        haystack = "\n".join(texts).casefold()
        matched: Dict[str, str] = {}
        for source, target in self.glossary.items():
            key = (source or "").strip()
            if not key or not target:
                continue
            if key.casefold() not in haystack:
                continue
            matched[key] = target
            if len(matched) >= MAX_PROMPT_TERMS:
                break
        return matched

    async def _translate_subset(
        self,
        texts: List[str],
        context: str,
        terms: Optional[Dict[str, str]] = None,
    ) -> List[Optional[str]]:
        """Faz uma chamada ao provedor e devolve a lista alinhada de traduções."""
        system_prompt = (
            "Você é um tradutor profissional especializado em tradução literária "
            "do inglês para português do Brasil.\n"
            "Regras:\n"
            "- Traduza com naturalidade, mantendo o tom e o estilo originais\n"
            "- Preserve nomes próprios e termos técnicos quando não houver tradução consagrada\n"
            "- Mantenha expressões idiomáticas apropriadas ao PT-BR\n"
            "- Não adicione explicações, comentários ou notas\n"
            "- Não invente informação que não esteja no segmento\n"
            "- Não troque o agente da ação: mantenha quem pratica e quem recebe\n"
            "- O contexto serve apenas para entender pronomes e referências; "
            "não o traduza nem o repita\n"
            "- Cada segmento recebe um marcador [[n]]; reproduza o mesmo marcador "
            "imediatamente antes da tradução correspondente\n"
            "- Preserve pontuação, aspas e estrutura quando possível"
        )

        if terms:
            listing = "; ".join(
                f"{source} = {target}" for source, target in terms.items()
            )
            system_prompt += (
                "\nGlossário obrigatório (use exatamente estas traduções):\n"
                f"{listing}"
            )

        header = f"Contexto: {context}\n\n" if context else ""
        numbered = "\n\n".join(
            f"[[{position}]] {text}" for position, text in enumerate(texts, start=1)
        )
        user_prompt = (
            f"{header}Traduza cada segmento abaixo para português do Brasil.\n"
            "Responda apenas com os segmentos traduzidos, cada um precedido pelo "
            "mesmo marcador [[n]] e na mesma ordem:\n\n"
            f"{numbered}"
        )

        try:
            if self.provider == "openai":
                content = await self._call_openai(system_prompt, user_prompt)
            elif self.provider == "ollama":
                content = await self._call_ollama(system_prompt, user_prompt)
            elif self.provider == "gemini":
                content = await self._call_gemini(system_prompt, user_prompt)
            else:
                # Provedor desconhecido: mantém os textos originais
                return list(texts)
        except TranslationCallError:
            raise
        except Exception as e:
            # Qualquer falha inesperada do provedor é tratada como falha de
            # infraestrutura (não adianta subdividir o lote).
            self._record_error(f"{self.provider}: {e}")
            raise TranslationCallError(str(e))

        return self._parse_response(content, len(texts))

    def _parse_response(self, content: Optional[str], count: int) -> List[Optional[str]]:
        """Extrai as traduções da resposta, alinhando-as por marcador [[n]]."""
        if not content or not content.strip():
            return [None] * count

        cleaned = content.strip()
        # Remove cercas de código que alguns modelos adicionam
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()

        chunks = NUMBER_MARKER_PATTERN.split(cleaned)
        # chunks = [prefixo, num, texto, num, texto, ...]
        parsed: Dict[int, str] = {}
        for position in range(1, len(chunks) - 1, 2):
            try:
                number = int(chunks[position])
            except ValueError:
                continue
            text = chunks[position + 1].strip()
            if text and 1 <= number <= count and number not in parsed:
                parsed[number] = text

        if parsed:
            return [parsed.get(index + 1) for index in range(count)]

        # Compatibilidade: modelos que ainda respeitam o separador antigo
        for separator in LEGACY_SEPARATORS:
            segments = [segment.strip() for segment in cleaned.split(separator)]
            if len(segments) == count and all(segments):
                return segments

        # Último recurso: um único segmento aceita a resposta crua
        if count == 1:
            return [cleaned]

        return [None] * count

    @staticmethod
    def _looks_untranslated(source: str, translated: str) -> bool:
        return looks_untranslated(source, translated)

    def _record_error(self, message: str) -> None:
        if len(self.errors) < self._max_errors:
            self.errors.append(message)
            print(message)

    async def _call_openai(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            self._record_error("OpenAI: api_key não informada")
            raise TranslationCallError("api_key ausente")

        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url or None)
            response = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=settings.translation_temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            self._record_error(f"OpenAI: {e}")
            raise TranslationCallError(str(e))

    async def _call_ollama(self, system_prompt: str, user_prompt: str) -> str:
        try:
            base_url = self.base_url or "http://localhost:11434"
            async with httpx.AsyncClient(timeout=600.0) as client:
                response = await client.post(
                    f"{base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "stream": False,
                        "options": {
                            "temperature": settings.translation_temperature,
                            # Sem num_ctx explícito o Ollama usa um valor baixo
                            # e trunca a resposta, o que também quebrava a
                            # segmentação de lotes grandes.
                            "num_ctx": settings.translation_num_ctx,
                            # Limita a geração: evita loop de repetição que
                            # consome o contexto inteiro e trava o lote.
                            "num_predict": settings.translation_num_predict,
                            "repeat_penalty": settings.translation_repeat_penalty,
                        }
                    }
                )
                response.raise_for_status()
                data = response.json()
            if data.get("error"):
                raise RuntimeError(str(data["error"]))
            message = data.get("message") or {}
            content = message.get("content") or ""
            if not content.strip():
                raise RuntimeError("resposta vazia do Ollama")
            return content
        except Exception as e:
            self._record_error(f"Ollama: {e}")
            raise TranslationCallError(str(e))

    async def _call_gemini(self, system_prompt: str, user_prompt: str) -> str:
        if not self.api_key:
            self._record_error("Gemini: api_key não informada")
            raise TranslationCallError("api_key ausente")

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(self.model)
            prompt = f"{system_prompt}\n\n{user_prompt}"
            response = model.generate_content(prompt)
            return response.text or ""
        except Exception as e:
            self._record_error(f"Gemini: {e}")
            raise TranslationCallError(str(e))
