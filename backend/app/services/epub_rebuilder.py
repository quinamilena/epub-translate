import uuid
from pathlib import Path
from typing import Dict, Any
from ebooklib import ITEM_DOCUMENT, ITEM_NAVIGATION, epub
from bs4 import BeautifulSoup


class EpubRebuilder:
    def __init__(self, output_dir: str = "./outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def _head_info(self, content: bytes) -> Dict[str, Any]:
        """Extrai título e links de CSS do <head>, que o ebooklib descarta."""
        soup = BeautifulSoup(content, 'lxml')

        title_tag = soup.find('title')
        title = title_tag.get_text(strip=True) if title_tag else None

        links = []
        for tag in soup.find_all('link', href=True):
            rel = tag.get('rel') or []
            if isinstance(rel, str):
                rel = [rel]
            if 'stylesheet' in [r.lower() for r in rel]:
                links.append({
                    'href': tag['href'],
                    'rel': 'stylesheet',
                    'type': tag.get('type') or 'text/css'
                })

        return {'title': title, 'links': links}

    def rebuild(self, original_book: epub.EpubBook, translated_items: Dict[str, str], new_title: str = None) -> str:
        # Criar novo livro
        new_book = epub.EpubBook()
        
        # Metadados
        new_book.set_identifier(str(uuid.uuid4()))
        new_book.set_title(new_title or "Translated Book")
        new_book.set_language('pt-BR')
        new_book.add_author('Translated')
        
        # Reaproveitar os itens originais (CSS, imagens, fontes, capa...)
        # Preserva classe, mídia e propriedades do EPUB (como cover-image).
        # Recriar um EpubItem genérico a partir do código numérico do tipo
        # descartava as imagens: no ebooklib imagem = 1, estilo = 2 e
        # capa = 10, então apenas o CSS era copiado.
        for item in original_book.get_items():
            try:
                item_type = item.get_type()
            except Exception:
                continue

            # Documentos XHTML são processados no laço seguinte;
            # a navegação é regenerada por EpubNcx/EpubNav.
            if item_type in (ITEM_DOCUMENT, ITEM_NAVIGATION):
                continue

            new_book.add_item(item)

        # <meta name="cover"> identifica a capa no EPUB2. Sem ela, alguns
        # leitores exibem o livro sem capa mesmo com a imagem presente.
        for value, attrs in original_book.get_metadata('OPF', 'cover'):
            new_book.add_metadata('OPF', 'cover', value, attrs)
        
        # Processar capítulos XHTML com tradução
        spine_items = []
        for item in original_book.get_items():
            try:
                item_type = item.get_type()
            except Exception:
                continue
            if item_type == ITEM_DOCUMENT:
                content = item.get_content()
                file_name = item.get_name()
                
                # Aplicar tradução se disponível
                if file_name in translated_items:
                    content = translated_items[file_name].encode('utf-8')
                else:
                    # Mesmo sem tradução, processar para garantir encoding
                    soup = BeautifulSoup(content, 'lxml')
                    content = str(soup).encode('utf-8')
                
                info = self._head_info(content)
                new_item = epub.EpubHtml(
                    uid=item.get_id(),
                    file_name=file_name,
                    lang='pt-BR',
                    title=info.get('title') or new_title or 'Livro Traduzido',
                    content=content
                )
                # O ebooklib descarta o <head> original ao remontar o documento,
                # então é preciso repassar os links de CSS para não perder o estilo
                for link in info.get('links', []):
                    new_item.add_link(**link)
                new_book.add_item(new_item)
                spine_items.append(new_item)
        
        # Navegação
        new_book.toc = original_book.toc
        new_book.add_item(epub.EpubNcx())
        new_book.add_item(epub.EpubNav())
        
        # Spine
        new_book.spine = ['nav'] + spine_items
        
        # Gerar arquivo
        output_filename = f"translated_{uuid.uuid4()}.epub"
        output_path = self.output_dir / output_filename
        epub.write_epub(str(output_path), new_book, {})
        
        return str(output_path)
