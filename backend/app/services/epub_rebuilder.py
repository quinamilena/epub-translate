import os
import uuid
from pathlib import Path
from typing import Dict, Any
from ebooklib import epub
from bs4 import BeautifulSoup


class EpubRebuilder:
    def __init__(self, output_dir: str = "./outputs"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def rebuild(self, original_book: epub.EpubBook, translated_items: Dict[str, str], new_title: str = None) -> str:
        # Criar novo livro
        new_book = epub.EpubBook()
        
        # Metadados
        new_book.set_identifier(str(uuid.uuid4()))
        new_book.set_title(new_title or "Translated Book")
        new_book.set_language('pt-BR')
        new_book.add_author('Translated')
        
        # Copiar CSS e imagens inalterados
        for item in original_book.get_items():
            try:
                item_type = item.get_type()
            except Exception:
                continue
            try:
                media_type = getattr(item, 'media_type', None) or getattr(item, 'mediaType', None) or 'text/css'
            except Exception:
                media_type = 'text/css'
            if item_type == 3:  # ITEM_STYLE
                new_item = epub.EpubItem(
                    uid=item.get_id(),
                    file_name=item.get_name(),
                    media_type=media_type,
                    content=item.get_content()
                )
                new_book.add_item(new_item)
            elif item_type == 2:  # ITEM_IMAGE
                try:
                    media_type = getattr(item, 'media_type', None) or getattr(item, 'mediaType', None) or item.get_media_type()
                except Exception:
                    media_type = getattr(item, 'media_type', 'image/jpeg')
                new_item = epub.EpubItem(
                    uid=item.get_id(),
                    file_name=item.get_name(),
                    media_type=media_type,
                    content=item.get_content()
                )
                new_book.add_item(new_item)
            elif item_type == 0:  # ITEM_COVER
                try:
                    media_type = getattr(item, 'media_type', None) or getattr(item, 'mediaType', None)
                except Exception:
                    media_type = None
                if not media_type:
                    media_type = 'image/jpeg'
                new_item = epub.EpubItem(
                    uid=item.get_id(),
                    file_name=item.get_name(),
                    media_type=media_type,
                    content=item.get_content()
                )
                new_book.add_item(new_item)
        
        # Processar capítulos XHTML com tradução
        spine_items = []
        for item in original_book.get_items():
            try:
                item_type = item.get_type()
            except Exception:
                continue
            if item_type == 9:  # ITEM_DOCUMENT
                content = item.get_content()
                file_name = item.get_name()
                
                # Aplicar tradução se disponível
                if file_name in translated_items:
                    content = translated_items[file_name].encode('utf-8')
                else:
                    # Mesmo sem tradução, processar para garantir encoding
                    soup = BeautifulSoup(content, 'lxml')
                    content = str(soup).encode('utf-8')
                
                new_item = epub.EpubHtml(
                    uid=item.get_id(),
                    file_name=file_name,
                    lang='pt-BR',
                    content=content
                )
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
