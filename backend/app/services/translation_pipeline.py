import asyncio
import json
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

from ebooklib import epub

from app.core.config import settings
from app.repositories.block_repository import BlockRepository
from app.repositories.chapter_repository import ChapterRepository
from app.repositories.job_repository import JobRepository
from app.services.epub_parser import PARSER_VERSION, EpubParser, read_zip_entry
from app.services.epub_rebuilder import EpubRebuilder
from app.services.epub_validator import EpubValidator
from app.services.translator import Translator, looks_untranslated
from app.utils.cleanup import cleanup_old_files


class DatabaseTranslatedItems:
    """Mapeamento preguiçoso `file_name -> XHTML traduzido`.

    O rebuilder percorre os documentos e pede um por vez; assim apenas um
    capítulo fica em memória durante a montagem. As traduções vêm do banco.
    """

    def __init__(self, source_path: str, parser: EpubParser, chapters, block_repo: BlockRepository):
        self.source_path = source_path
        self.parser = parser
        self.block_repo = block_repo
        self.chapters = {chapter["file_name"]: chapter for chapter in chapters}

    def __contains__(self, file_name: str) -> bool:
        return file_name in self.chapters

    def __getitem__(self, file_name: str) -> str:
        chapter = self.chapters[file_name]
        source = read_zip_entry(self.source_path, file_name)
        blocks, soup = self.parser.extract_translatable_blocks(source)

        translations = {
            block["block_index"]: block["translated_text"]
            for block in self.block_repo.list_by_chapter(chapter["id"])
            if block["translated_text"]
        }

        for block in blocks:
            translated = translations.get(block["index"])
            if not translated:
                continue
            tag = soup.find(attrs=block["attrs"])
            if tag:
                tag.string = translated

        self.parser.strip_markers(soup)
        return str(soup)


class TranslationPipeline:
    def __init__(self):
        self.job_repo = JobRepository()
        self.chapter_repo = ChapterRepository()
        self.block_repo = BlockRepository()
        self.parser = EpubParser(settings.upload_dir, settings.temp_dir)
        self.rebuilder = EpubRebuilder(settings.output_dir)
        self.validator = EpubValidator()
        # A GPU/Ollama é gargalo único: processa um job por vez.
        self._lock = asyncio.Lock()

    async def run(self, job_id: str, api_key: Optional[str] = None) -> None:
        async with self._lock:
            try:
                await self._run(job_id, api_key)
            except Exception as exc:
                traceback.print_exc()
                self.job_repo.update(
                    job_id, status="error", error=str(exc), message=f"Erro: {exc}"
                )
            finally:
                self._cleanup_storage()

    async def _run(self, job_id: str, api_key: Optional[str]) -> None:
        job = self.job_repo.get(job_id)
        if not job:
            return
        if job["status"] == "cancelled":
            return
        if (
            job["status"] == "done"
            and self.block_repo.count_status(job_id, "failed") == 0
        ):
            return

        source_path = job["source_path"]
        if not source_path or not Path(source_path).exists():
            raise FileNotFoundError(f"Arquivo fonte não encontrado: {source_path}")

        if self.chapter_repo.count(job_id) == 0:
            self._ingest(job_id, source_path)
            if self._is_cancelled(job_id):
                self.job_repo.update(
                    job_id, status="cancelled", message="Tradução cancelada"
                )
                return
            self.job_repo.update(
                job_id, status="translating", message="Traduzindo conteúdo..."
            )
        else:
            if self._is_cancelled(job_id):
                self.job_repo.update(
                    job_id, status="cancelled", message="Tradução cancelada"
                )
                return
            self.job_repo.update(
                job_id, status="translating", message="Retomando tradução..."
            )
            self.block_repo.reset_failed(job_id)

        job = self.job_repo.get(job_id)
        translator = Translator(
            provider=job["provider"],
            model=job["model"],
            api_key=api_key or settings.translation_api_key,
            base_url=job["base_url"],
            glossary_name=job["glossary"],
        )

        completed = await self._translate(job_id, translator)
        if not completed:
            self.job_repo.update(
                job_id, status="cancelled", message="Tradução cancelada"
            )
            return

        done = self.block_repo.count_status(job_id, "done")
        failed = self.block_repo.count_status(job_id, "failed")
        if done == 0 and failed > 0:
            errors = translator.errors[:10] or self.block_repo.errors(job_id, limit=10)
            self.job_repo.update(
                job_id,
                status="error",
                message=(
                    "Nenhum bloco foi traduzido. Verifique o provedor e retome."
                ),
                errors_json=json.dumps(errors, ensure_ascii=False) if errors else None,
            )
            return

        self.job_repo.update(
            job_id, status="rebuilding", progress=85, message="Reconstruindo EPUB..."
        )
        output_path = self._assemble(job_id)

        self.job_repo.update(
            job_id, status="validating", progress=95, message="Validando EPUB..."
        )
        validation = self.validator.validate(output_path)

        failed = self.block_repo.count_status(job_id, "failed")
        errors = translator.errors[:10] or self.block_repo.errors(job_id, limit=10)

        message = "Concluído!"
        if validation.get("valid") is False:
            message = f"Concluído com avisos - {validation.get('message')}"
        if failed:
            message += f" ({failed} bloco(s) sem tradução)"
        if errors:
            message += f" ({len(errors)} erro(s) do tradutor)"

        self.job_repo.update(
            job_id,
            status="done",
            progress=100,
            message=message,
            output_path=output_path,
            validation_json=json.dumps(validation, ensure_ascii=False),
            errors_json=json.dumps(errors, ensure_ascii=False) if errors else None,
            done_blocks=self.block_repo.count_status(job_id, "done"),
            done_chapters=self.chapter_repo.count_done(job_id),
        )

        if settings.purge_translation_payload and failed == 0:
            self.job_repo.purge_payload(job_id)

    def _ingest(self, job_id: str, source_path: str) -> None:
        self.job_repo.update(
            job_id, status="extracting", progress=5, message="Extraindo EPUB..."
        )

        book = epub.read_epub(source_path)
        try:
            source_title = None
            try:
                titles = book.get_metadata("DC", "title")
                if titles:
                    source_title = titles[0][0]
            except Exception:
                source_title = None

            documents = []
            for item in book.get_items():
                try:
                    item_type = item.get_type()
                except Exception:
                    continue
                if item_type == 9:  # ITEM_DOCUMENT
                    documents.append(
                        {"item_id": item.get_id(), "file_name": item.get_name()}
                    )

            if not documents:
                raise ValueError("Nenhum documento XHTML encontrado no EPUB")

            self.chapter_repo.bulk_create(job_id, documents)
            chapters = self.chapter_repo.list_by_job(job_id)

            total_blocks = 0
            for index, chapter in enumerate(chapters):
                content = read_zip_entry(source_path, chapter["file_name"])
                blocks, _ = self.parser.extract_translatable_blocks(content)
                self.block_repo.bulk_insert(job_id, chapter["id"], blocks)
                total_blocks += len(blocks)
                if not blocks:
                    self.chapter_repo.set_status(chapter["id"], "done")
                progress = 5 + int((index + 1) / len(chapters) * 15)
                self.job_repo.update(
                    job_id,
                    progress=progress,
                    message=f"Extraindo {index + 1}/{len(chapters)} capítulos...",
                )

            self.job_repo.update(
                job_id,
                progress=20,
                source_title=source_title,
                total_chapters=len(chapters),
                total_blocks=total_blocks,
                parser_version=PARSER_VERSION,
            )
        finally:
            del book

    async def _translate(self, job_id: str, translator: Translator) -> bool:
        job = self.job_repo.get(job_id)
        total_blocks = job["total_blocks"] or 1
        chapters = self.chapter_repo.list_by_job(job_id)

        for chapter in chapters:
            if self._is_cancelled(job_id):
                return False
            if chapter["status"] == "done":
                continue

            self.chapter_repo.set_status(chapter["id"], "translating")
            pending = self.block_repo.list_by_chapter(chapter["id"], only_pending=True)
            texts = [block["source_text"] for block in pending]

            if not texts:
                self.chapter_repo.set_status(chapter["id"], "done")
                continue

            for batch_indices in self._chunk_indices(texts, settings.chunk_size):
                if self._is_cancelled(job_id):
                    return False

                batch = [pending[index] for index in batch_indices]
                translated = await translator.translate_batch(
                    [block["source_text"] for block in batch],
                    context=f"Capítulo: {chapter['file_name']}",
                )

                updates = []
                for block, output in zip(batch, translated):
                    if output is None or looks_untranslated(
                        block["source_text"], output
                    ):
                        updates.append(
                            {
                                "id": block["id"],
                                "translated_text": None,
                                "status": "failed",
                                "error": "bloco não traduzido",
                            }
                        )
                    else:
                        updates.append(
                            {
                                "id": block["id"],
                                "translated_text": output,
                                "status": "done",
                                "error": None,
                            }
                        )
                # Ponto de retomada: cada lote é confirmado no banco.
                self.block_repo.save_translations(updates)

                done = self.block_repo.count_status(job_id, "done")
                progress = 20 + int(55 * done / total_blocks)
                self.job_repo.update(
                    job_id,
                    progress=progress,
                    done_blocks=done,
                    message=f"Traduzindo {chapter['file_name']}...",
                )

            chapter_failed = self.block_repo.count_status_for_chapter(
                chapter["id"], "failed"
            )
            self.chapter_repo.set_status(
                chapter["id"], "partial" if chapter_failed else "done"
            )
            self.job_repo.update(
                job_id, done_chapters=self.chapter_repo.count_done(job_id)
            )

        return True

    def _assemble(self, job_id: str) -> str:
        job = self.job_repo.get(job_id)
        chapters = self.chapter_repo.list_by_job(job_id)
        translated_items = DatabaseTranslatedItems(
            job["source_path"], self.parser, chapters, self.block_repo
        )

        book = epub.read_epub(job["source_path"])
        try:
            new_title = job["source_title"] or "Livro Traduzido"
            return self.rebuilder.rebuild(book, translated_items, new_title)
        finally:
            del book

    def _is_cancelled(self, job_id: str) -> bool:
        job = self.job_repo.get(job_id)
        return job is None or job["status"] == "cancelled"

    @staticmethod
    def _chunk_indices(texts: List[str], max_chars: int) -> List[List[int]]:
        batches: List[List[int]] = []
        current: List[int] = []
        size = 0
        for index, text in enumerate(texts):
            if current and size + len(text) > max_chars:
                batches.append(current)
                current, size = [], 0
            current.append(index)
            size += len(text)
        if current:
            batches.append(current)
        return batches

    def _cleanup_storage(self) -> None:
        removed_uploads = cleanup_old_files(
            settings.upload_dir, settings.upload_retention_days
        )
        removed_outputs = cleanup_old_files(
            settings.output_dir, settings.output_retention_days
        )
        if removed_uploads or removed_outputs:
            print(
                f"Limpeza de armazenamento: {removed_uploads} upload(s), "
                f"{removed_outputs} output(s) removidos"
            )
