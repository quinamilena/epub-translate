import os
import uuid
import zipfile
from pathlib import Path
from typing import Dict, List, Any
from ebooklib import epub
from bs4 import BeautifulSoup


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
        for i, tag in enumerate(soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'td', 'th', 'blockquote', 'figcaption'])):
            text = tag.get_text(strip=True)
            if text and len(text) > 2:
                blocks.append({
                    "index": i,
                    "tag": tag.name,
                    "original": str(tag),
                    "text": text,
                    "attrs": dict(tag.attrs)
                })
        return blocks, soup
