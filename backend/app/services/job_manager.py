import os
import uuid
import asyncio
from pathlib import Path
from typing import Dict, Any
from app.services.epub_parser import EpubParser
from app.services.translator import Translator
from app.services.epub_rebuilder import EpubRebuilder
from app.services.epub_validator import EpubValidator
from app.core.config import settings
from bs4 import BeautifulSoup


class JobManager:
    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.extracted_cache: Dict[str, Dict[str, Any]] = {}
        self.parser = EpubParser(settings.upload_dir, settings.temp_dir)
        self.rebuilder = EpubRebuilder(settings.output_dir)
        self.validator = EpubValidator()
    
    def create_job(self, filename: str) -> str:
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "progress": 0,
            "message": "Job criado",
            "filename": filename,
            "download_url": None
        }
        return job_id
    
    def get_job(self, job_id: str) -> Dict[str, Any]:
        job = self.jobs.get(job_id)
        if not job:
            return {"status": "error", "message": "Job não encontrado"}
        # Retornar cópia sem objetos pesados
        safe_job = dict(job)
        safe_job.pop('extracted_data', None)
        return safe_job
    
    async def process_job(self, job_id: str, file_path: str, translation_config: Dict[str, Any] = None):
        try:
            self.jobs[job_id]["status"] = "extracting"
            self.jobs[job_id]["progress"] = 10
            self.jobs[job_id]["message"] = "Extraindo EPUB..."
            
            extracted = self.parser.extract(Path(file_path))
            self.extracted_cache[job_id] = extracted
            
            self.jobs[job_id]["status"] = "translating"
            self.jobs[job_id]["progress"] = 30
            self.jobs[job_id]["message"] = "Traduzindo conteúdo..."
            
            translator = Translator(
                provider=translation_config.get("provider") if translation_config else None,
                model=translation_config.get("model") if translation_config else None,
                api_key=translation_config.get("api_key") if translation_config else None,
                base_url=translation_config.get("base_url") if translation_config else None,
            )
            
            translated_items = {}
            xhtml_items = extracted["xhtml_items"]
            total = len(xhtml_items)
            
            for idx, xhtml_item in enumerate(xhtml_items):
                file_name = xhtml_item["file_name"]
                content = xhtml_item["content"]
                
                blocks, soup = self.parser.extract_translatable_blocks(content)
                
                if blocks:
                    texts_to_translate = [b["text"] for b in blocks]
                    # Traduzir em lotes
                    translated_texts = await translator.translate_batch(texts_to_translate, context=f"Capítulo: {file_name}")
                    
                    # Aplicar traduções
                    for block, translated in zip(blocks, translated_texts):
                        # Encontrar e substituir o texto
                        tag = soup.find(block["tag"], attrs=block["attrs"])
                        if tag and translated != block["text"]:
                            tag.string = translated
                    
                    translated_items[file_name] = str(soup)
                else:
                    translated_items[file_name] = content.decode('utf-8')
                
                progress = 30 + int((idx + 1) / total * 50)
                self.jobs[job_id]["progress"] = progress
                self.jobs[job_id]["message"] = f"Traduzindo {idx+1}/{total} capítulos..."
            
            self.jobs[job_id]["status"] = "rebuilding"
            self.jobs[job_id]["progress"] = 85
            self.jobs[job_id]["message"] = "Reconstruindo EPUB..."
            
            # Título traduzido
            new_title = "Livro Traduzido"
            if extracted["metadata"].get("title"):
                titles = extracted["metadata"]["title"]
                if titles:
                    try:
                        if titles[0] and len(titles[0]) > 0:
                            new_title = str(titles[0][0])
                    except:
                        pass
            
            output_path = self.rebuilder.rebuild(extracted["book"], translated_items, new_title)
            
            self.jobs[job_id]["status"] = "validating"
            self.jobs[job_id]["progress"] = 95
            self.jobs[job_id]["message"] = "Validando EPUB..."
            
            validation = self.validator.validate(output_path)
            self.jobs[job_id]["validation"] = validation
            
            self.jobs[job_id]["status"] = "done"
            self.jobs[job_id]["progress"] = 100
            if validation.get("valid") is False:
                self.jobs[job_id]["message"] = f"Concluído com avisos - {validation.get('message')}"
            else:
                self.jobs[job_id]["message"] = "Concluído!"
            self.jobs[job_id]["download_url"] = f"/download/{Path(output_path).name}"
            self.jobs[job_id]["output_path"] = output_path
            
            # Limpar cache após conclusão
            if job_id in self.extracted_cache:
                del self.extracted_cache[job_id]
            
        except Exception as e:
            self.jobs[job_id]["status"] = "error"
            self.jobs[job_id]["progress"] = 0
            self.jobs[job_id]["message"] = f"Erro: {str(e)}"
            print(f"Job error: {e}")
            import traceback
            traceback.print_exc()


job_manager = JobManager()
