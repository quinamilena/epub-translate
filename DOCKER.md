# README - Docker

## Pré-requisitos
- [Docker](https://www.docker.com/get-started)
- [Docker Compose](https://docs.docker.com/compose/)

## Subir aplicação

### 1. Clonar/ter o projeto
Já está em `C:\Users\Milena\Documents\epub-translate`

### 2. Baixar modelo Ollama (primeira vez)
Após subir os containers, baixe o modelo:

```bash
docker exec -it epub-ollama ollama pull llama3.1
```

Ou outros modelos: `llama3.2`, `mistral`, `gemma2`, etc.

### 3. Subir containers
```bash
docker-compose up -d --build
```

Aguarde alguns minutos na primeira build (instalação de dependências + epubcheck).

### 4. Acessar aplicação
- **Frontend**: http://localhost:5500
- **Backend API**: http://localhost:8000
- **Documentação**: http://localhost:8000/docs
- **Ollama**: http://localhost:11434

## Comandos úteis

```bash
# Ver logs
docker-compose logs -f

# Ver logs apenas do backend
docker-compose logs -f backend

# Parar containers
docker-compose down

# Parar e remover volumes (limpa modelos Ollama)
docker-compose down -v

# Rebuild sem cache
docker-compose build --no-cache

# Entrar no container backend
docker exec -it epub-backend bash

# Ver modelos instalados no Ollama
docker exec -it epub-ollama ollama list
```

## Configuração sem GPU
Se não tiver GPU NVIDIA, o arquivo `docker-compose.yml` já está configurado sem a seção `deploy`. O Ollama funcionará na CPU (mais lento, mas funcional).

## Volumes
- `ollama_data` - Modelos baixados do Ollama (persistente)
- `./backend/uploads` - Arquivos enviados
- `./backend/outputs` - EPUBs traduzidos
- `./backend/glossaries` - Glossários criados
- `./backend/tmp` - Arquivos temporários

## Troubleshooting

**Erro de conexão com Ollama:**
- Verifique se o modelo foi baixado: `docker exec -it epub-ollama ollama list`
- Aguarde o Ollama iniciar completamente

**Porta já em uso:**
- Altere as portas no `docker-compose.yml` (ex: "5501:80", "8001:8000")

**Memória insuficiente:**
- Modelos como llama3.1 precisam ~4-8GB RAM
- Use modelos menores: `ollama pull llama3.2:3b`
- Altere o modelo no frontend para o modelo instalado
