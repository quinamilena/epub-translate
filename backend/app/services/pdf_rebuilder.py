import html
import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pymupdf
from ebooklib import epub

from app.repositories.block_repository import BlockRepository


# Imagens menores que isso normalmente são ícones, filetes ou artefatos.
IMAGE_MIN_SIZE = 40

# Imagem que ocupa boa parte da largura da página entra na posição vertical
# extraída do PDF; as demais vão para o fim da seção para não quebrar o texto.
FULL_WIDTH_RATIO = 0.6

# Imagens que cobrem quase toda a página são fundos de digitalização. Mantê-las
# duplicaria a página inteira atrás do texto traduzido.
FULL_PAGE_RATIO = 0.9

ALLOWED_TAGS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "li"}

IMAGE_MEDIA_TYPES = {
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "png": "image/png",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tiff": "image/tiff",
    "tif": "image/tiff",
    "webp": "image/webp",
    "jp2": "image/jp2",
    "jpx": "image/jpx",
}


class PdfRebuilder:
    def __init__(self, output_dir: str = "./outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def rebuild(
        self,
        source_path: str,
        chapters: List[Dict[str, Any]],
        block_repo: BlockRepository,
        source_title: Optional[str] = None,
    ) -> str:
        doc = pymupdf.open(source_path)
        try:
            book = epub.EpubBook()
            book.set_identifier(str(uuid.uuid4()))

            metadata = doc.metadata or {}
            title = (
                source_title
                or (metadata.get("title") or "").strip()
                or Path(source_path).stem
                or "PDF Traduzido"
            )
            book.set_title(title)
            book.set_language("pt-BR")

            author = (metadata.get("author") or "").strip()
            book.add_author(author or "Desconhecido")

            self._add_style(book)
            images = self._extract_images(doc, book)

            spine_items: List[epub.EpubHtml] = []
            for index, chapter in enumerate(chapters):
                blocks = block_repo.list_by_chapter(chapter["id"])
                start, end = self._page_range(chapter)
                page_images = [
                    image
                    for image in images
                    if start <= image["page"] <= end
                ]
                content, section_title = self._render_section(
                    chapter, blocks, page_images, start, index
                )
                item = epub.EpubHtml(
                    uid=f"pdf-section-{index + 1:04d}",
                    file_name=chapter["file_name"],
                    lang="pt-BR",
                    title=section_title,
                    content=content,
                )
                item.add_link(
                    href="style.css", rel="stylesheet", type="text/css"
                )
                book.add_item(item)
                spine_items.append(item)

            book.toc = tuple(spine_items)
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())
            book.spine = ["nav"] + spine_items

            output_filename = f"translated_{uuid.uuid4()}.epub"
            output_path = self.output_dir / output_filename
            epub.write_epub(str(output_path), book, {})
            return str(output_path)
        finally:
            doc.close()

    # ------------------------------------------------------------------
    # Semântica do capítulo/seção
    # ------------------------------------------------------------------

    @staticmethod
    def _page_range(chapter: Dict[str, Any]) -> Tuple[int, int]:
        item_id = chapter.get("item_id") or ""
        match = re.search(r"pdf:pages:(\d+)-(\d+)", item_id)
        if match:
            return int(match.group(1)), int(match.group(2))

        match = re.search(r"(\d+)-(\d+)", chapter.get("file_name") or "")
        if match:
            return int(match.group(1)), int(match.group(2))

        return 1, 1

    @staticmethod
    def _block_meta(block: Dict[str, Any]) -> Dict[str, Any]:
        raw = block.get("meta_json")
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _pick_title(
        self,
        blocks: List[Dict[str, Any]],
        chapter: Dict[str, Any],
        index: int,
    ) -> str:
        for block in blocks:
            kind = block.get("kind") or ""
            if kind in {"h1", "h2", "h3"}:
                text = self._clean_text(
                    block.get("translated_text")
                    or block.get("source_text")
                    or ""
                ).strip()
                if text:
                    return text[:120]

        title = (chapter.get("title") or "").strip()
        return title[:120] if title else f"Seção {index + 1}"

    # ------------------------------------------------------------------
    # XHTML
    # ------------------------------------------------------------------

    def _render_section(
        self,
        chapter: Dict[str, Any],
        blocks: List[Dict[str, Any]],
        page_images: List[Dict[str, Any]],
        start_page: int,
        index: int,
    ) -> Tuple[str, str]:
        section_title = self._pick_title(blocks, chapter, index)

        entries: List[Tuple[int, float, int, Dict[str, Any]]] = []
        for block in blocks:
            meta = self._block_meta(block)
            page = int(meta.get("page") or start_page)
            bbox = meta.get("bbox") or [0, 0, 0, 0]
            y = float(bbox[1]) if len(bbox) > 1 else 0.0
            entries.append((page, y, 0, block))

        tail_images: List[Dict[str, Any]] = []
        for image in page_images:
            if image["full_width"]:
                entries.append((image["page"], image["y"], 1, image))
            else:
                tail_images.append(image)

        entries.sort(key=lambda entry: (entry[0], entry[1], entry[2]))

        parts: List[str] = []
        current_page: Optional[int] = None
        for page, _, kind, item in entries:
            if current_page is not None and page != current_page:
                parts.append('<hr class="page-sep"/>')
            current_page = page

            if kind == 0:
                tag = item.get("kind") or "p"
                if tag not in ALLOWED_TAGS:
                    tag = "p"
                text = self._clean_text(
                    item.get("translated_text")
                    or item.get("source_text")
                    or ""
                ).strip()
                if not text:
                    continue
                parts.append(f"<{tag}>{html.escape(text)}</{tag}>")
            else:
                parts.append(self._figure(item))

        for image in tail_images:
            parts.append(self._figure(image))

        body = "\n".join(parts)
        # O ebooklib extrai os filhos de <body> e monta o documento final com
        # o template próprio, incluindo o <title> e os links de CSS.
        content = f"<html><body>{body}</body></html>"
        return content, section_title

    @staticmethod
    def _clean_text(text: str) -> str:
        """Remove caracteres de controle inválidos em XML/XHTML."""
        return "".join(
            char for char in text if char in "\n\t" or ord(char) >= 32
        )

    @staticmethod
    def _figure(image: Dict[str, Any]) -> str:
        source = html.escape(image["file_name"], quote=True)
        return (
            '<figure class="pdf-figure">'
            f'<img src="{source}" alt=""/>'
            "</figure>"
        )

    def _add_style(self, book: epub.EpubBook) -> None:
        css = """
body {
    line-height: 1.55;
    text-align: justify;
    margin: 0 5%;
}
h1, h2, h3 {
    text-align: left;
    line-height: 1.25;
    margin: 1.4em 0 0.6em;
}
p {
    margin: 0 0 0.85em;
}
figure.pdf-figure {
    margin: 1.2em 0;
    text-align: center;
}
figure.pdf-figure img {
    max-width: 100%;
    height: auto;
}
hr.page-sep {
    border: none;
    border-top: 1px solid #ccc;
    margin: 1.5em 10%;
}
"""
        book.add_item(
            epub.EpubItem(
                uid="pdf-style",
                file_name="style.css",
                media_type="text/css",
                content=css.encode("utf-8"),
            )
        )

    # ------------------------------------------------------------------
    # Imagens
    # ------------------------------------------------------------------

    def _extract_images(
        self, doc, book: epub.EpubBook
    ) -> List[Dict[str, Any]]:
        images: List[Dict[str, Any]] = []
        seen: set = set()

        for page_index in range(doc.page_count):
            page = doc[page_index]
            page_width = float(page.rect.width) or 1.0
            page_height = float(page.rect.height) or 1.0
            page_has_text = bool(page.get_text("text").strip())

            for image_info in page.get_images(full=True):
                xref = int(image_info[0])
                if xref in seen:
                    continue

                try:
                    extracted = doc.extract_image(xref)
                except Exception:
                    continue

                width = int(extracted.get("width") or 0)
                height = int(extracted.get("height") or 0)
                content = extracted.get("image")
                ext = (extracted.get("ext") or "").lower()
                media_type = IMAGE_MEDIA_TYPES.get(ext)

                if (
                    not content
                    or not media_type
                    or width < IMAGE_MIN_SIZE
                    or height < IMAGE_MIN_SIZE
                ):
                    continue

                rects = page.get_image_rects(xref)
                if rects:
                    rect = rects[0]
                    rect_width = float(rect.width)
                    rect_height = float(rect.height)
                    y = float(rect.y0)
                else:
                    rect_width = width
                    rect_height = height
                    y = page_height

                if (
                    page_has_text
                    and rect_width >= page_width * FULL_PAGE_RATIO
                    and rect_height >= page_height * FULL_PAGE_RATIO
                ):
                    # Fundo de página digitalizada: o texto traduzido já cobre
                    # o conteúdo e a imagem duplicaria a página inteira.
                    continue

                file_name = f"images/pdf-img-{xref:06d}.{ext}"
                try:
                    book.add_item(
                        epub.EpubItem(
                            uid=f"pdf-img-{xref}",
                            file_name=file_name,
                            media_type=media_type,
                            content=content,
                        )
                    )
                except Exception:
                    continue

                seen.add(xref)
                images.append(
                    {
                        "file_name": file_name,
                        "page": page_index + 1,
                        "y": y,
                        "full_width": rect_width
                        >= page_width * FULL_WIDTH_RATIO,
                    }
                )

        return images
