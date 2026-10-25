import subprocess
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional


class EpubValidator:
    def __init__(self, epubcheck_path: Optional[str] = None):
        self.epubcheck_path = epubcheck_path or self._find_epubcheck()
    
    def _find_epubcheck(self) -> Optional[str]:
        # Tentar encontrar epubcheck
        common_paths = [
            "epubcheck",
            "epubcheck.jar",
            os.path.expanduser("~/.local/bin/epubcheck"),
            "C:/epubcheck/epubcheck.jar"
        ]
        for path in common_paths:
            try:
                result = subprocess.run([path, "--version"], capture_output=True, timeout=5)
                if result.returncode == 0:
                    return path
            except:
                continue
        return None
    
    def validate(self, epub_path: str) -> Dict[str, Any]:
        if not self.epubcheck_path:
            return {
                "valid": None,
                "message": "epubcheck não encontrado. Instale epubcheck para validação completa.",
                "errors": [],
                "warnings": []
            }
        
        try:
            result = subprocess.run(
                [self.epubcheck_path, epub_path],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            output = result.stdout + result.stderr
            
            errors = []
            warnings = []
            for line in output.split('\n'):
                if 'ERROR' in line.upper():
                    errors.append(line.strip())
                elif 'WARNING' in line.upper():
                    warnings.append(line.strip())
            
            return {
                "valid": result.returncode == 0,
                "message": "Válido" if result.returncode == 0 else f"{len(errors)} erro(s) encontrado(s)",
                "errors": errors[:10],  # Limitar
                "warnings": warnings[:10],
                "full_output": output[:1000]
            }
        except subprocess.TimeoutExpired:
            return {
                "valid": None,
                "message": "Timeout na validação",
                "errors": [],
                "warnings": []
            }
        except Exception as e:
            return {
                "valid": None,
                "message": f"Erro na validação: {str(e)}",
                "errors": [],
                "warnings": []
            }
