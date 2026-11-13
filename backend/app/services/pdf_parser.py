import math
import re
import statistics
import unicodedata
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pymupdf


# Versão do algoritmo de extração de PDF. Muda se a extração deixar de ser
# determinística; jobs antigos não podem ser retomados se isso divergir.
PDF_PARSER_VERSION = 1

# Abaixo disso o PDF é tratado como digitalizado (sem camada de texto).
MIN_TEXT_CHARS = 200

# Seções muito grandes são divididas para melhorar progresso e retomada.
MAX_SECTION_PAGES = 25

# Faixa vertical considerada margem para remover cabeçalhos/rodapés.
MARGIN_RATIO = 0.12

# Um texto de margem precisa aparecer em pelo menos esta fração das páginas
# (e no mínimo em duas) para ser considerado cabeçalho/rodapé repetido.
HEADER_FOOTER_RATIO = 0.35
MIN_REPEATED_PAGES = 2
MAX_MARGIN_TEXT = 120

# Detecção de títulos por tamanho de fonte em relação ao corpo do texto.
HEADING_H1_RATIO = 1.28
HEADING_H2_RATIO = 1.10
MAX_HEADING_CHARS = 160


class PdfParser:
    def __init__(
        self,
        min_text_chars: int = MIN_TEXT_CHARS,
        max_section_pages: int = MAX_SECTION_PAGES,
    ):
        self.min_text_chars = min_text_chars
        self.max_section_pages = max_section_pages

    def validate_pdf(self, file_path: Path) -> None:
        """Abre o PDF e falha com mensagem clara quando ele não é utilizável."""
        try:
            doc = pymupdf.open(str(file_path))
        except Exception as exc:
            raise ValueError("Não foi possível abrir o PDF.") from exc

        try:
            if doc.needs_pass:
                raise ValueError("PDF protegido por senha não é suportado.")
            if doc.page_count == 0:
                raise ValueError("O PDF não possui páginas.")
        finally:
            doc.close()

    def extract(self, file_path: Path) -> Dict[str, Any]:
        """Extrai texto, seções e metadados do PDF.

        Retorna uma estrutura equivalente à do EpubParser, mas com seções
        (páginas ou capítulos identificados pelo sumário do PDF) em vez de
        documentos XHTML.
        """
        file_path = Path(file_path)

        try:
            doc = pymupdf.open(str(file_path))
        except Exception as exc:
            raise ValueError("Não foi possível abrir o PDF.") from exc

        try:
            if doc.needs_pass:
                raise ValueError("PDF protegido por senha não é suportado.")
            if doc.page_count == 0:
                raise ValueError("O PDF não possui páginas.")

            pages = [
                self._extract_page(doc, page_number)
                for page_number in range(1, doc.page_count + 1)
            ]
            self._remove_running_headers(pages)
            self._merge_paragraph_fragments(pages)

            total_chars = sum(
                len(block["text"])
                for page in pages
                for block in page["blocks"]
            )
            if total_chars < self.min_text_chars:
                raise ValueError(
                    "PDF sem camada de texto. OCR não é suportado nesta versão."
                )

            self._classify_blocks(pages)
            sections = self._build_sections(doc, pages)
            if not any(section["blocks"] for section in sections):
                raise ValueError("Nenhum texto extraído do PDF.")

            return {
                "metadata": self._extract_metadata(doc, file_path),
                "sections": sections,
            }
        finally:
            doc.close()

    # ------------------------------------------------------------------
    # Extração por página
    # ------------------------------------------------------------------

    def _extract_page(self, doc, page_number: int) -> Dict[str, Any]:
        page = doc[page_number - 1]
        width = float(page.rect.width)
        height = float(page.rect.height)

        raw = page.get_text("dict", sort=True)
        blocks: List[Dict[str, Any]] = []

        for block in raw.get("blocks", []):
            if block.get("type") != 0:  # 0 = texto; 1 = imagem
                continue

            lines = []
            for line in block.get("lines", []):
                spans = line.get("spans", [])
                text = "".join(span.get("text", "") for span in spans)
                # NFKC corrige ligaduras tipográficas (ﬁ, ﬂ) que quebrariam
                # a tradução e a busca no texto.
                text = unicodedata.normalize("NFKC", text)
                text = text.replace("\u00ad", "")
                text = self._sanitize_text(text)
                if not text.strip():
                    continue

                lines.append(
                    {
                        "text": text,
                        "size": max(
                            (
                                float(span.get("size") or 0)
                                for span in spans
                            ),
                            default=0.0,
                        ),
                        "bold": any(
                            int(span.get("flags") or 0) & 16
                            for span in spans
                        ),
                    }
                )

            if not lines:
                continue

            text = self._join_lines([line["text"] for line in lines])
            if not text:
                continue

            bbox = tuple(
                float(value) for value in (block.get("bbox") or (0, 0, 0, 0))
            )
            blocks.append(
                {
                    "text": text,
                    "bbox": bbox,
                    "size": max(line["size"] for line in lines),
                    "bold": any(line["bold"] for line in lines),
                    "page": page_number,
                    "page_width": width,
                    "page_height": height,
                }
            )

        return {
            "number": page_number,
            "width": width,
            "height": height,
            "blocks": blocks,
        }

    @staticmethod
    def _sanitize_text(text: str) -> str:
        """Remove caracteres de controle inválidos em XML/XHTML."""
        return "".join(
            char for char in text if char in "\n\t" or ord(char) >= 32
        )

    @staticmethod
    def _join_lines(lines: Sequence[str]) -> str:
        """Junta linhas de um parágrafo corrigindo hifenização de fim de linha."""
        result = ""
        for raw in lines:
            text = re.sub(r"\s+", " ", raw).strip()
            if not text:
                continue

            if not result:
                result = text
                continue

            # "transla-\nção" -> "translação"; já "Anglo-\nSaxon" mantém o
            # hífen porque o próximo trecho começa com maiúscula.
            if (
                result.endswith("-")
                and len(result) > 1
                and text[:1].islower()
            ):
                result = result[:-1] + text
            else:
                result = f"{result} {text}"

        return result.strip()

    # ------------------------------------------------------------------
    # Cabeçalhos, rodapés e números de página
    # ------------------------------------------------------------------

    @staticmethod
    def _in_margin(block: Dict[str, Any], page: Dict[str, Any]) -> bool:
        _, y0, _, y1 = block["bbox"]
        height = page["height"] or 1
        return y0 <= height * MARGIN_RATIO or y1 >= height * (1 - MARGIN_RATIO)

    @staticmethod
    def _margin_key(text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        normalized = re.sub(r"\d+", "#", normalized)
        normalized = re.sub(r"[^\w#]+", " ", normalized)
        return re.sub(r"\s+", " ", normalized).strip()

    @staticmethod
    def _is_page_number(text: str) -> bool:
        text = text.strip()
        if len(text) > 24:
            return False
        patterns = (
            r"^(?:page\s*)?[-–—]?\s*\d{1,4}\s*[-–—]?$",
            r"^(?:page\s*)?[-–—]?\s*[ivxlcdm]{1,8}\s*[-–—]?$",
        )
        return any(re.fullmatch(pattern, text, re.IGNORECASE) for pattern in patterns)

    def _remove_running_headers(self, pages: List[Dict[str, Any]]) -> None:
        """Remove cabeçalhos/rodapés repetidos e números de página.

        A contagem é feita em duas etapas para não depender da página atual:
        primeiro identifica os textos que se repetem nas margens, depois
        filtra os blocos.
        """
        occurrences: Dict[str, set] = {}
        for page in pages:
            for block in page["blocks"]:
                if not self._in_margin(block, page):
                    continue
                if len(block["text"]) > MAX_MARGIN_TEXT:
                    continue
                key = self._margin_key(block["text"])
                if not key:
                    continue
                occurrences.setdefault(key, set()).add(page["number"])

        threshold = max(
            MIN_REPEATED_PAGES,
            math.ceil(len(pages) * HEADER_FOOTER_RATIO),
        )
        repeated = {
            key
            for key, page_numbers in occurrences.items()
            if len(page_numbers) >= threshold
        }

        for page in pages:
            kept = []
            for block in page["blocks"]:
                if self._in_margin(block, page):
                    key = self._margin_key(block["text"])
                    if key in repeated or self._is_page_number(block["text"]):
                        continue
                kept.append(block)
            page["blocks"] = kept

    # ------------------------------------------------------------------
    # Junção de fragmentos de parágrafo
    # ------------------------------------------------------------------

    @staticmethod
    def _horizontal_overlap(
        first: Dict[str, Any], second: Dict[str, Any]
    ) -> float:
        first_x0, _, first_x1, _ = first["bbox"]
        second_x0, _, second_x1, _ = second["bbox"]
        overlap = min(first_x1, second_x1) - max(first_x0, second_x0)
        smaller = min(first_x1 - first_x0, second_x1 - second_x0)
        return overlap / smaller if smaller > 0 else 0.0

    def _merge_paragraph_fragments(
        self, pages: List[Dict[str, Any]]
    ) -> None:
        """Une blocos que são linhas do mesmo parágrafo.

        O PyMuPDF às vezes devolve cada linha (ou grupo de linhas) como um
        bloco separado. Sem essa junção, um parágrafo vira várias tags <p>
        no EPUB e a tradução perde coesão.
        """
        for page in pages:
            blocks = sorted(page["blocks"], key=lambda block: block["bbox"][1])
            merged: List[Dict[str, Any]] = []

            for block in blocks:
                if not merged:
                    merged.append(block)
                    continue

                previous = merged[-1]
                previous_size = previous["size"] or 0
                current_size = block["size"] or 0
                sizes = [size for size in (previous_size, current_size) if size]
                reference_size = max(sizes) if sizes else 10.0
                gap = block["bbox"][1] - previous["bbox"][3]
                size_ratio = (
                    max(previous_size, current_size)
                    / max(min(previous_size, current_size), 0.1)
                )

                if (
                    gap <= reference_size * 0.45
                    and size_ratio <= 1.15
                    and self._horizontal_overlap(previous, block) >= 0.5
                ):
                    previous["text"] = self._join_lines(
                        [previous["text"], block["text"]]
                    )
                    previous["bbox"] = (
                        min(previous["bbox"][0], block["bbox"][0]),
                        min(previous["bbox"][1], block["bbox"][1]),
                        max(previous["bbox"][2], block["bbox"][2]),
                        max(previous["bbox"][3], block["bbox"][3]),
                    )
                    previous["size"] = max(previous_size, current_size)
                    previous["bold"] = previous["bold"] and block["bold"]
                    continue

                merged.append(block)

            page["blocks"] = merged

    # ------------------------------------------------------------------
    # Classificação de parágrafos e títulos
    # ------------------------------------------------------------------

    def _classify_blocks(self, pages: List[Dict[str, Any]]) -> None:
        sizes: List[float] = []
        for page in pages:
            for block in page["blocks"]:
                # Peso maior para blocos longos: o corpo do texto domina a
                # mediana, enquanto títulos curtos não distorcem o cálculo.
                weight = max(1, min(len(block["text"]), 200) // 20)
                sizes.extend([block["size"] or 0.0] * weight)

        body_size = statistics.median(sizes) if sizes else 10.0
        if body_size <= 0:
            body_size = 10.0

        for page in pages:
            for block in page["blocks"]:
                text = block["text"].strip()
                size = block["size"] or body_size
                short = len(text) <= MAX_HEADING_CHARS
                ends_sentence = bool(re.search(r"[.,;:]$", text))

                if (
                    short
                    and not ends_sentence
                    and size >= body_size * HEADING_H1_RATIO
                ):
                    block["tag"] = "h1"
                elif (
                    short
                    and not ends_sentence
                    and (
                        size >= body_size * HEADING_H2_RATIO
                        or (block["bold"] and size >= body_size * 1.05)
                    )
                ):
                    block["tag"] = "h2"
                else:
                    block["tag"] = "p"

    # ------------------------------------------------------------------
    # Seções (sumário do PDF ou uma página por seção)
    # ------------------------------------------------------------------

    def _build_sections(
        self, doc, pages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        page_count = len(pages)
        starts = self._toc_starts(self._safe_toc(doc), page_count)

        sections: List[Dict[str, Any]] = []
        if starts:
            if starts[0][1] > 1:
                starts.insert(0, ("Front matter", 1))
            for index, (title, start) in enumerate(starts):
                end = (
                    starts[index + 1][1] - 1
                    if index + 1 < len(starts)
                    else page_count
                )
                if end < start:
                    continue
                sections.extend(self._split_section(title, start, end))
        else:
            for page_number in range(1, page_count + 1):
                sections.append(
                    {"title": None, "start": page_number, "end": page_number}
                )

        blocks_by_page = {
            page["number"]: page["blocks"] for page in pages
        }
        result: List[Dict[str, Any]] = []

        for index, section in enumerate(sections):
            blocks: List[Dict[str, Any]] = []
            for page_number in range(section["start"], section["end"] + 1):
                for block in blocks_by_page.get(page_number, []):
                    blocks.append(
                        {
                            "index": len(blocks),
                            "tag": block["tag"],
                            "text": block["text"],
                            "meta": {
                                "page": block["page"],
                                "bbox": list(block["bbox"]),
                                "font_size": round(block["size"], 2),
                            },
                        }
                    )

            result.append(
                {
                    "file_name": f"section-{index + 1:04d}.xhtml",
                    "item_id": f"pdf:pages:{section['start']}-{section['end']}",
                    "title": section["title"],
                    "blocks": blocks,
                }
            )

        return result

    @staticmethod
    def _safe_toc(doc) -> List[Any]:
        try:
            return doc.get_toc(simple=True) or []
        except Exception:
            return []

    def _toc_starts(
        self, toc: Sequence[Any], page_count: int
    ) -> List[Tuple[str, int]]:
        """Extrai do sumário do PDF os títulos que iniciam seções."""
        if not toc:
            return []

        entries: List[Tuple[int, str, int]] = []
        for item in toc:
            if len(item) < 3:
                continue
            level, title, page = item[0], item[1], item[2]
            title = (title or "").strip()
            try:
                page = int(page)
            except (TypeError, ValueError):
                continue
            if not title or page < 1:
                continue
            entries.append((int(level), title, min(page, page_count)))

        if len(entries) < 2:
            return []

        min_level = min(level for level, _, _ in entries)
        candidates = [
            (title, page)
            for level, title, page in entries
            if level == min_level
        ]

        # Alguns PDFs têm apenas um item de nível superior com os capítulos
        # no nível seguinte.
        if len(candidates) < 2:
            next_levels = [
                level for level, _, _ in entries if level > min_level
            ]
            if next_levels:
                next_level = min(next_levels)
                candidates = [
                    (title, page)
                    for level, title, page in entries
                    if level == next_level
                ]

        candidates.sort(key=lambda item: item[1])
        starts: List[Tuple[str, int]] = []
        for title, page in candidates:
            if starts and page <= starts[-1][1]:
                continue
            starts.append((title, page))

        return starts if len(starts) >= 2 else []

    def _split_section(
        self, title: Optional[str], start: int, end: int
    ) -> List[Dict[str, Any]]:
        if end - start + 1 <= self.max_section_pages:
            return [{"title": title, "start": start, "end": end}]

        parts: List[Dict[str, Any]] = []
        part_number = 1
        for chunk_start in range(start, end + 1, self.max_section_pages):
            chunk_end = min(
                chunk_start + self.max_section_pages - 1, end
            )
            part_title = (
                f"{title} ({part_number})" if title else None
            )
            parts.append(
                {
                    "title": part_title,
                    "start": chunk_start,
                    "end": chunk_end,
                }
            )
            part_number += 1
        return parts

    def _extract_metadata(
        self, doc, file_path: Path
    ) -> Dict[str, Any]:
        metadata = doc.metadata or {}
        title = (metadata.get("title") or "").strip()
        if not title or title.casefold() in {"untitled", "unknown"}:
            title = file_path.stem or "PDF Traduzido"

        author = (metadata.get("author") or "").strip() or None
        return {
            "title": title,
            "author": author,
            "page_count": doc.page_count,
        }
