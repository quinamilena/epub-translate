import os
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Any
from ebooklib import epub
from bs4 import BeautifulSoup, Comment, NavigableString


# Atributo temporário usado para localizar cada bloco de forma única
MARKER_ATTR = "data-tr-idx"

# Versão do algoritmo de extração. Muda se a extração deixar de ser
# determinística; jobs antigos não podem ser retomados se isso divergir.
PARSER_VERSION = 1

# Tags cujo texto é traduzido
TRANSLATABLE_TAGS = ['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'td', 'th', 'blockquote', 'figcaption']

# Tags que nunca fazem parte do texto traduzido e não devem ser preservadas
# na distribuição da tradução
IGNORED_CHILD_TAGS = ('script', 'style')


def _split_proportional(text: str, weights: List[int]) -> List[str]:
    """Divide `text` em partes proporcionais aos pesos informados.

    Usado para recolocar a tradução nos nós de texto originais sem perder
    imagens, quebras e outros elementos intercalados. O corte acontece em
    limites de palavra para não fragmentar o texto.
    """
    words = text.split()
    if not words:
        return [''] * len(weights)

    total = sum(weights) or 1
    parts: List[str] = []
    start = 0
    accumulated = 0
    for position, weight in enumerate(weights):
        accumulated += weight
        if position == len(weights) - 1:
            end = len(words)
        else:
            end = round(len(words) * accumulated / total)
            end = max(start, min(end, len(words)))
        parts.append(' '.join(words[start:end]))
        start = end
    return parts


def _block_text(tag) -> str:
    """Monta o texto do bloco preservando as fronteiras entre as palavras.

    `get_text(strip=True)` remove o espaço de cada nó antes de concatenar e
    gruda palavras separadas por tags inline ("He wasveryangry"). Aqui os nós
    são unidos como estão no documento e apenas espaços repetidos são
    normalizados; `<br>` é convertido em separador.
    """
    pieces = []
    for node in tag.descendants:
        if isinstance(node, Comment):
            continue
        if isinstance(node, NavigableString):
            pieces.append(str(node))
        elif getattr(node, 'name', None) == 'br':
            pieces.append(' ')
    return ' '.join(''.join(pieces).split())


def read_zip_entry(epub_path: str, file_name: str) -> bytes:
    """Lê um documento diretamente do ZIP, sem carregar o livro inteiro, lidando com caminhos relativos."""
    with zipfile.ZipFile(epub_path) as archive:
        names = archive.namelist()
        if file_name in names:
            return archive.read(file_name)
        
        cleaned_name = file_name.lstrip('/')
        for name in names:
            if name.lstrip('/') == cleaned_name or name.endswith('/' + cleaned_name):
                return archive.read(name)
        
        return archive.read(file_name)


class EpubParser:
    def __init__(self, upload_dir: str = "./uploads", temp_dir: str = "./tmp"):
        self.upload_dir = Path(upload_dir)
        self.temp_dir = Path(temp_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    def validate_epub(self, file_path: Path) -> bool:
        try:
            if not zipfile.is_zipfile(file_path):
                return False
            book = epub.read_epub(str(file_path))
            return book is not None
        except Exception:
            return False
    
    def extract(self, file_path: Path) -> Dict[str, Any]:
        job_id = str(uuid.uuid4())
        work_dir = self.temp_dir / job_id
        work_dir.mkdir(parents=True, exist_ok=True)
        
        book = epub.read_epub(str(file_path))
        
        items = {
            "job_id": job_id,
            "work_dir": str(work_dir),
            "book": book,
            "xhtml_items": [],
            "images": [],
            "styles": [],
            "metadata": {},
            "toc": []
        }
        
        # Metadados
        for key in ['title', 'creator', 'language', 'identifier']:
            try:
                items["metadata"][key] = book.get_metadata('DC', key)
            except:
                items["metadata"][key] = []
        
        # Itens
        for item in book.get_items():
            try:
                item_type = item.get_type()
            except Exception:
                continue
            if item_type == 9:  # ITEM_DOCUMENT
                items["xhtml_items"].append({
                    "id": item.get_id(),
                    "file_name": item.get_name(),
                    "content": item.get_content(),
                    "item": item
                })
            elif item_type == 2:  # ITEM_IMAGE
                items["images"].append({
                    "id": item.get_id(),
                    "file_name": item.get_name(),
                    "content": item.get_content(),
                    "item": item
                })
            elif item_type == 3:  # ITEM_STYLE
                items["styles"].append({
                    "id": item.get_id(),
                    "file_name": item.get_name(),
                    "content": item.get_content(),
                    "item": item
                })
        
        # TOC
        try:
            toc = book.toc
            items["toc"] = self._flatten_toc(toc)
        except:
            items["toc"] = []
        
        return items
    
    def _flatten_toc(self, toc, level=0):
        result = []
        for item in toc:
            if isinstance(item, tuple):
                section, children = item
                result.append({"title": getattr(section, 'title', str(section)), "href": getattr(section, 'href', ''), "level": level})
                result.extend(self._flatten_toc(children, level+1))
            else:
                result.append({"title": getattr(item, 'title', str(item)), "href": getattr(item, 'href', ''), "level": level})
        return result
    
    def extract_translatable_blocks(self, xhtml_content: bytes) -> List[Dict[str, Any]]:
        soup = BeautifulSoup(xhtml_content, 'lxml')
        blocks = []
        # Remover scripts/styles
        for tag in soup(['script', 'style']):
            tag.decompose()
        
        # Blocos translatáveis
        for i, tag in enumerate(soup.find_all(TRANSLATABLE_TAGS)):
            # Quando um bloco contém outro bloco translatável (ex.:
            # <blockquote><p>), apenas o interno é traduzido. Sem isso, aplicar
            # a tradução no bloco externo destruiria os marcadores dos filhos e
            # as traduções deles seriam perdidas silenciosamente.
            if tag.find(TRANSLATABLE_TAGS):
                continue
            # Junta o texto dos nós preservando as fronteiras entre palavras;
            # concatenar com strip grudava palavras separadas por tags inline
            # ("He wasveryangry").
            text = _block_text(tag)
            if text and len(text) > 2:
                # Marcador único: sem isso, tags com os mesmos atributos
                # são resolvidas sempre para o primeiro elemento do documento
                marker = f"tr-{i}"
                tag[MARKER_ATTR] = marker
                blocks.append({
                    "index": i,
                    "tag": tag.name,
                    "original": str(tag),
                    "text": text,
                    "attrs": {MARKER_ATTR: marker}
                })
        return blocks, soup

    def apply_translation(self, tag, translated: str) -> None:
        """Aplica a tradução a um bloco sem descartar seu conteúdo interno.

        `tag.string = tradução` apaga tudo que existe dentro da tag: imagens,
        quebras de linha, marcações de página e links. Quando o bloco tem
        elementos internos, a tradução é distribuída entre os nós de texto
        originais, proporcionalmente à quantidade de palavras de cada um, para
        que esses elementos permaneçam nas mesmas posições.
        """
        children = [
            child
            for child in tag.find_all(True)
            if child.name not in IGNORED_CHILD_TAGS
        ]
        if not children:
            tag.string = translated
            return

        text_nodes = [
            node
            for node in tag.find_all(string=True)
            if isinstance(node, NavigableString)
            and not isinstance(node, Comment)
            and node.strip()
        ]
        if not text_nodes:
            tag.append(translated)
            return

        originals = [str(node) for node in text_nodes]
        parts = _split_proportional(
            translated, [len(text.split()) for text in originals]
        )
        for index, (node, part) in enumerate(zip(text_nodes, parts)):
            original = originals[index]
            leading = original[: len(original) - len(original.lstrip())]
            trailing = original[len(original.rstrip()):]
            following = next(
                (item for item in parts[index + 1:] if item), None
            )
            # A fronteira entre dois nós pode não ter espaço no original
            # ("</strong>: texto"). Como a divisão é feita em palavras, sem
            # isso as palavras ficariam coladas ao remontar o bloco.
            if (
                part
                and following
                and not trailing
                and not originals[index + 1].startswith(' ')
                and part[-1].isalnum()
                and following[0].isalnum()
            ):
                trailing = ' '
            node.replace_with(f"{leading}{part}{trailing}")

    def strip_markers(self, soup: BeautifulSoup) -> None:
        """Remove os marcadores internos antes de serializar o XHTML."""
        for tag in soup.find_all(attrs={MARKER_ATTR: True}):
            del tag[MARKER_ATTR]
