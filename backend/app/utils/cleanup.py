import time
from pathlib import Path


def cleanup_old_files(directory: str, max_age_days: int) -> int:
    """Remove arquivos mais antigos que max_age_days do diretório.

    Retorna a quantidade de arquivos removidos. Arquivos ocultos de
    controle (por exemplo .gitkeep) são preservados.
    """
    if not max_age_days or max_age_days <= 0:
        return 0

    path = Path(directory)
    if not path.is_dir():
        return 0

    cutoff = time.time() - (max_age_days * 86400)
    removed = 0

    for entry in path.iterdir():
        if entry.name.startswith('.'):
            continue
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                entry.unlink()
                removed += 1
        except OSError:
            continue

    return removed
