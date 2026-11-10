## Modo de execução padrão (sem Docker)

- O projeto deve ser executado **sem Docker** por padrão. Não usar `docker compose` para subir esta aplicação.
- Backend (rodar de dentro de `backend`): `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- Frontend (rodar da raiz): `.\backend\.venv\Scripts\python.exe -m http.server 5500 --directory frontend`
- Acessar em http://localhost:5500 (API em http://localhost:8000, health check `/api/health`).
- Usar o Python do venv (`.venv\Scripts\python.exe`); o `python` do PATH abre a Microsoft Store.
- `backend/.env` define o provedor de tradução; o Ollama local precisa estar no ar em `http://localhost:11434` para traduzir.

## Windows 11 Terminal Compatibility

- The development environment is Windows 11 using PowerShell. Always generate commands compatible with PowerShell.
- Never use Unix/Linux-specific commands such as `tail`, `head`, `grep`, `sed`, `awk`, or `cat` when executing commands in PowerShell.
- Use PowerShell equivalents instead: `Select-Object -Last N` for `tail -N`, `Select-Object -First N` for `head -N`, `Select-String` for `grep`, and `Get-Content` for `cat`.
- When chaining commands, use PowerShell-compatible syntax and operators.
- Before executing a command, verify that its syntax and utilities are compatible with the current shell.
- Do not assume Bash, Unix utilities, or WSL are available unless explicitly confirmed.
- When using Docker commands with PowerShell pipelines, avoid interactive flags such as `-it` when they interfere with piped output.
- If a command fails because of shell incompatibility, rewrite it for the current environment instead of retrying the same command.
