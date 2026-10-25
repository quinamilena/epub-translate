# EPUB Translate - Inglês para Português BR

Aplicativo para traduzir livros EPUB do inglês para português brasileiro, preservando capítulos, sumário (TOC), imagens, CSS e formatação original.

## Arquitetura

- **Backend**: FastAPI (Python)
- **Frontend**: HTML/CSS/JavaScript estático
- **Parser**: ebooklib + BeautifulSoup
- **Tradução**: Ollama (padrão), OpenAI, Google Gemini
- **Reconstrução**: ebooklib
- **Validação**: epubcheck (opcional)

## Instalação

### Backend

```bash
cd backend
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
# source venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
```

### Configuração (.env)

Padrão configurado para **Ollama local**:

```env
TRANSLATION_PROVIDER=ollama
TRANSLATION_MODEL=llama3.1
TRANSLATION_BASE_URL=http://localhost:11434
```

Certifique-se de ter o Ollama rodando e o modelo baixado:
```bash
ollama pull llama3.1
ollama serve
```

## Executar

### Terminal 1 - Backend
```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Acesse: http://localhost:8000/docs

### Terminal 2 - Frontend
```bash
cd frontend
python -m http.server 5500
```

Acesse: http://localhost:5500

## Como usar

1. Inicie o Ollama com um modelo (ex: llama3.1)
2. Abra o frontend no navegador
3. Selecione seu arquivo .EPUB em inglês
4. Verifique as configurações (já pré-configuradas para Ollama)
5. Clique em "Traduzir Livro"
6. Aguarde o processamento (extração → tradução → reconstrução → validação)
7. Baixe o EPUB traduzido

## Funcionalidades

- ✅ Upload de EPUB
- ✅ Extração de capítulos, imagens, CSS
- ✅ Tradução por blocos com preservação de contexto
- ✅ Reconstrução mantendo estrutura original
- ✅ Preservação de TOC/sumário
- ✅ Preservação de imagens
- ✅ Interface web simples
- ✅ Processamento assíncrono
- ✅ **Suporte a glossário customizável**
- ✅ **Validação com epubcheck**
- ✅ **Pré-configurado com Ollama local**

## API Endpoints

- `POST /api/upload` - Upload e inicia tradução
- `GET /api/status/{job_id}` - Status do processamento
- `GET /api/download/{filename}` - Download do EPUB traduzido
- `GET /api/glossaries` - Lista glossários
- `POST /api/glossaries` - Cria glossário
- `GET /api/health` - Health check

## Glossário

Crie glossários para manter consistência em termos técnicos/nomes:

```json
POST /api/glossaries
{
  "name": "fantasy",
  "entries": {
    "Warden": "Guardião",
    "Guild": "Guilda"
  }
}
```

## Validação

Para validação completa com epubcheck:
1. Baixe [epubcheck](https://github.com/w3c/epubcheck/releases)
2. Adicione ao PATH ou coloque em `C:/epubcheck/epubcheck.jar`
3. O validador detectará automaticamente

## Limitações

- Tradução literária pode variar conforme modelo do Ollama
- Livros muito grandes podem demorar (processamento assíncrono)
- epubcheck opcional para validação

## Roadmap

- [x] Suporte a glossário
- [x] Tradução com cache (planejado)
- [ ] Melhor tratamento de notas de rodapé
- [x] Validação com epubcheck
- [ ] Modo batch
- [ ] Suporte a mais provedores
- [ ] Preview por capítulo
