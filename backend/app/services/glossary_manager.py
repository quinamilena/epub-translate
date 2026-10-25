import os
import json
from pathlib import Path
from typing import Dict, List, Any


class GlossaryManager:
    def __init__(self, glossary_dir: str = "./glossaries"):
        self.glossary_dir = Path(glossary_dir)
        self.glossary_dir.mkdir(parents=True, exist_ok=True)
    
    def create_glossary(self, name: str, entries: Dict[str, str]) -> str:
        glossary_path = self.glossary_dir / f"{name}.json"
        data = {
            "name": name,
            "entries": entries,
            "count": len(entries)
        }
        with open(glossary_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return str(glossary_path)
    
    def load_glossary(self, name: str) -> Dict[str, str]:
        glossary_path = self.glossary_dir / f"{name}.json"
        if not glossary_path.exists():
            return {}
        try:
            with open(glossary_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("entries", {})
        except:
            return {}
    
    def list_glossaries(self) -> List[Dict[str, Any]]:
        glossaries = []
        for file in self.glossary_dir.glob("*.json"):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    glossaries.append({
                        "name": file.stem,
                        "count": data.get("count", 0)
                    })
            except:
                pass
        return glossaries
    
    def apply_glossary(self, text: str, glossary: Dict[str, str]) -> str:
        if not glossary:
            return text
        result = text
        # Aplicar substituições (case-sensitive por padrão, palavras inteiras quando possível)
        for source, target in glossary.items():
            # Substituição simples
            result = result.replace(source, target)
        return result
