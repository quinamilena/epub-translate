# EPUB Translate — Inglês para Português BR

Aplicativo para traduzir livros **EPUB e PDF** do inglês para o português brasileiro. EPUBs preservam capítulos, sumário (TOC), imagens, CSS e a formatação original. PDFs são extraídos e convertidos em um EPUB traduzido.

- **Backend:** FastAPI (Python) + SQLite
- **Frontend:** HTML/CSS/JavaScript estático
- **Parser/Reconstrução:** ebooklib + BeautifulSoup + PyMuPDF
- **Tradução:** Ollama (local), OpenAI ou Google Gemini
- **Validação:** epubcheck (opcional; incluso na imagem Docker)

Este README mostra como rodar **sem Docker** e **com Docker**, a diferença entre os dois modos, qual escolher em cada cenário e a **configuração mínima para traduzir**.

---

## Como funciona o processamento

1. Upload do EPUB ou PDF.
2. Extração de capítulos/páginas, blocos de texto, imagens e CSS.
3. Tradução por lotes (`CHUNK_SIZE` caracteres por chamada). Cada lote recebe os parágrafos anteriores como contexto (apenas para resolver pronomes e referências — eles não são traduzidos). A quantidade vem do seletor **Contexto** na tela (padrão: 2 parágrafos).
4. Reconstrução do EPUB preservando estrutura, capa, imagens e estilos (no caso de PDF, o EPUB é gerado a partir das páginas).
5. Validação com epubcheck (quando disponível).
6. Download do EPUB traduzido.

### Glossário de termos

O glossário fixa terminologia (por exemplo, `firebending` → `dobra de fogo`). Os termos presentes em cada lote entram no prompt de tradução e, se o modelo deixar algum termo em inglês, são substituídos no resultado.

- A interface lista os glossários disponíveis em `backend/glossaries/*.json` no seletor **Glossário de termos**.
- Incluído: `avatar.json`, com termos do universo Avatar (dobras, nações, títulos).
- Para criar outro: `POST /api/glossaries` com `{"name": "meu-livro", "entries": {"termo EN": "termo PT"}}`, ou edite o JSON direto.

### Formatos aceitos

| Entrada | Saída | Observação |
|---|---|---|
| `.epub` | `.epub` | Estrutura, capa, imagens e CSS originais preservados |
| `.pdf` | `.epub` | Texto e imagens são extraídos e reorganizados; o layout fixo do PDF não é mantido |

PDFs digitalizados (sem camada de texto) **não são suportados** nesta versão, porque exigiriam OCR. O app informa o erro e o job pode ser cancelado.

O processamento é assíncrono e cada etapa é persistida no banco (`backend/data/epub_translate.db`). Se algo falhar, o job pode ser **retomado** sem recomeçar do zero.

> O pipeline processa **um job por vez**. Isso evita saturar a GPU/RAM do Ollama e mantém o uso de memória previsível. A concorrência interna é assíncrona (`async/await`), não multiprocessos.

### Pausar e retomar

- **Pausar** interrompe a tradução ao terminar o lote atual (alguns segundos) e mantém todos os blocos já traduzidos. O job fica com status `paused`.
- **Retomar** continua exatamente de onde parou: capítulos concluídos são pulados e só os blocos pendentes são traduzidos.
- **Cancelar** é diferente: marca o job como `cancelled`. Também é possível retomar depois, mas o status final fica registrado como cancelado até a retomada.
- Se o backend cair ou for reiniciado com um job ativo, ele é marcado como `paused` automaticamente e pode ser retomado pela tela.

---

## Estrutura do projeto

```
epub-translate/
├── backend/
│   ├── app/                 # código FastAPI
│   ├── uploads/             # EPUBs enviados
│   ├── outputs/             # EPUBs traduzidos
│   ├── tmp/                 # arquivos temporários
│   ├── glossaries/          # glossários
│   ├── data/                # banco SQLite
│   ├── .env.example
│   └── requirements.txt
├── frontend/                # index.html, app.js, styles.css
├── docker/nginx.conf
├── Dockerfile.backend
├── Dockerfile.frontend
└── docker-compose.yml
```

---

## Requisitos

### Comuns aos dois modos

- Um EPUB ou PDF de entrada.
- Um provedor de tradução configurado (veja a seção [Configuração mínima](#configuração-mínima-para-traduzir)).

### Para rodar sem Docker

- Python **3.11 ou 3.12**
- `pip`
- Opcional: **Ollama** instalado no host (se for usar tradução local)
- Opcional: **Java** + epubcheck (somente para validação completa)

### Para rodar com Docker

- **Docker Desktop** (Windows/macOS) ou Docker Engine + Compose (Linux)
- Docker Compose v2 (`docker compose`)
- Opcional: GPU NVIDIA com NVIDIA Container Toolkit (para acelerar o Ollama em container)

---

## Configuração mínima para traduzir

O arquivo de configuração é `backend/.env` (copie de `backend/.env.example`).

```powershell
Copy-Item backend\.env.example backend\.env
```

Só existem três caminhos possíveis de provedor. Escolha **um** deles.

### Opção 1 — Ollama local (gratuito, recomendado para uso pessoal)

```env
TRANSLATION_PROVIDER=ollama
TRANSLATION_MODEL=qwen2.5:14b-instruct
TRANSLATION_BASE_URL=http://localhost:11434
TRANSLATION_API_KEY=
```

Antes de traduzir, o modelo precisa existir no Ollama:

```powershell
ollama pull qwen2.5:14b-instruct
ollama serve
```

Alternativas mais leves (menos RAM/VRAM, tradução um pouco inferior):

```powershell
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5:3b-instruct
```

E ajuste `TRANSLATION_MODEL=qwen2.5:7b-instruct` (ou `qwen2.5:3b-instruct`).

> O 14B pede ~10–12 GB de VRAM/RAM livres e leva cerca do dobro do tempo do 7B, mas erra menos referentes e concordância. O 7B pede ~5–8 GB. Livros grandes usam mais contexto e demoram mais.

### Opção 2 — OpenAI

```env
TRANSLATION_PROVIDER=openai
TRANSLATION_MODEL=gpt-4o-mini
TRANSLATION_API_KEY=<OPENAI_API_KEY>
TRANSLATION_BASE_URL=
```

Nunca versione a chave real. O projeto não persiste a API key no banco: ela é usada apenas durante o job. Ao **retomar** um job, informe a chave novamente na tela.

### Opção 3 — Google Gemini

```env
TRANSLATION_PROVIDER=gemini
TRANSLATION_MODEL=gemini-2.0-flash
TRANSLATION_API_KEY=<GEMINI_API_KEY>
TRANSLATION_BASE_URL=
```

### Ajustes de desempenho e estabilidade (Ollama)

```env
TRANSLATION_NUM_CTX=8192
TRANSLATION_NUM_PREDICT=2048
TRANSLATION_REPEAT_PENALTY=1.15
TRANSLATION_TEMPERATURE=0.15
TRANSLATION_CONTEXT_BLOCKS=2
```

- `TRANSLATION_NUM_CTX`: janela de contexto enviada ao Ollama. Baixo demais trunca a resposta; alto demais consome RAM/VRAM.
- `TRANSLATION_NUM_PREDICT`: limite de tokens gerados por lote. **Não use `-1`**: se o modelo entrar em repetição, ele gera até estourar o contexto e o job parece travado.
- `TRANSLATION_REPEAT_PENALTY`: reduz loops de geração em modelos menores.
- `TRANSLATION_TEMPERATURE`: quanto menor, mais estável a tradução. Acima de ~0.3 o modelo pode trocar o referente de um pronome entre duas execuções do mesmo trecho.
- `TRANSLATION_CONTEXT_BLOCKS`: valor inicial do seletor **Contexto** (0–10 parágrafos). O valor escolhido na tela é gravado no job e reaproveitado ao retomar.

### Onde a configuração é aplicada: `.env` x tela

A tela possui os campos **Provedor**, **Modelo**, **Base URL**, **API Key**, **Glossário de termos** e **Contexto**. Eles são enviados junto com o upload e **têm prioridade sobre o `.env`** quando preenchidos.

- Deixe um campo vazio na tela para usar o valor do `.env`.
- O seletor **Contexto** define quantos parágrafos anteriores acompanham cada lote (0 a 10). Mais contexto ajuda em pronomes e referências, mas aumenta o prompt e o tempo por lote. O padrão é 2.
- A tela já vem preenchida com `ollama`, `qwen2.5:14b-instruct` e `http://localhost:11434`. Isso é ótimo no modo local, mas **precisa ser ajustado no modo Docker** (veja abaixo).
- Ao usar **OpenAI**, limpe o campo **Base URL** da tela (ou deixe-o vazio), porque a tela envia esse valor e ele sobrescreveria o endpoint correto da OpenAI.

---

## Rodar sem Docker (local)

### 1) Backend

```powershell
cd backend

# criar e ativar o ambiente virtual
# (se `python` abrir a Microsoft Store, use: py -3.12 -m venv .venv)
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# instalar dependências
pip install -r requirements.txt

# configurar
Copy-Item .env.example .env
# edite o .env conforme a seção de configuração mínima

# iniciar
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

O backend precisa rodar **de dentro da pasta `backend`**, porque os caminhos (`./uploads`, `./outputs`, `./data` etc.) e o `.env` são relativos ao diretório de execução.

Verificação:

- API: http://localhost:8000
- Documentação: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health → `{"status":"ok"}`

### 2) Frontend

Em outro terminal, na raiz do projeto:

```powershell
.\backend\.venv\Scripts\python.exe -m http.server 5500 --directory frontend
```

Acesse: **http://localhost:5500**

> No Windows, o comando `python` pode ser o atalho da Microsoft Store (que não executa nada). Por isso os exemplos usam o Python do ambiente virtual (`.venv\Scripts\python.exe`). Alternativa: usar o launcher `py -3.12`.

### Observações do modo local

- O frontend chama a API em `http://localhost:8000/api` (definido em `frontend/app.js`).
- O CORS padrão já libera `http://localhost:5500` e `http://127.0.0.1:5500`.
- O `--reload` reinicia o backend ao salvar arquivos, útil durante desenvolvimento.
- epubcheck é opcional: sem ele o job conclui, mas a validação retorna `valid: null` com aviso.

---

## Rodar com Docker

### 1) Configurar

```powershell
Copy-Item backend\.env.example backend\.env
```

O `docker-compose.yml` monta `backend/.env` no container, então o arquivo precisa existir. Ele também define variáveis de ambiente próprias (`TRANSLATION_PROVIDER`, `TRANSLATION_MODEL`, `TRANSLATION_BASE_URL`).

### 2) Subir os containers

```powershell
docker compose up -d --build
```

Na primeira execução a build demora mais (dependências Python + Java + epubcheck).

Serviços:

| Serviço | Porta no host | Descrição |
|---|---|---|
| `frontend` | 5500 | Nginx servindo o frontend |
| `backend` | 8000 | FastAPI + epubcheck |
| `ollama` | 11434 | Servidor Ollama em container |

### 3) Baixar o modelo dentro do container do Ollama

O Ollama do Docker é uma instância separada do Ollama do host. Os modelos precisam ser baixados **no container**:

```powershell
docker exec -it epub-ollama ollama pull qwen2.5:14b-instruct
```

> O `docker-compose.yml` define `translategemma:4b` como padrão **de ambiente**. Se você for usar o modelo padrão da tela (`qwen2.5:14b-instruct`), baixe esse. Se preferir usar o valor do Compose, baixe `translategemma:4b` ou ajuste `TRANSLATION_MODEL` no Compose. O ideal é manter o mesmo nome nos dois lugares.

### 4) Ajustar a tela (atenção)

Como os campos da tela sobrescrevem o `.env`:

- **Base URL** deve ser `http://ollama:11434` (nome do serviço na rede do Compose), e **não** `localhost`.
- **Modelo** deve ser o mesmo que você baixou no container.

Se preferir usar o **Ollama do host** (por exemplo, para aproveitar a GPU sem configurar passthrough):

- Mantenha o Ollama nativo rodando no host.
- Na tela, use `http://host.docker.internal:11434` (Windows/macOS).
- Opcionalmente, remova o serviço `ollama` do Compose.

### GPU no Docker

O Compose já traz o bloco de GPU comentado. Para habilitar (requer NVIDIA Container Toolkit):

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: all
          capabilities: [gpu]
```

Sem GPU, o Ollama em container roda em CPU (funciona, porém bem mais lento).

### Comandos úteis

```powershell
docker compose logs -f              # todos os logs
docker compose logs -f backend      # apenas backend
docker compose stop                 # parar
docker compose down                 # remover containers
docker compose down -v              # remover também o volume dos modelos Ollama
docker compose build --no-cache     # rebuild completo
docker exec -it epub-backend bash   # shell no backend
docker exec -it epub-ollama ollama list
```

---

## Diferenças entre rodar local e com Docker

| Aspecto | Sem Docker (local) | Com Docker |
|---|---|---|
| Instalação | Python, venv, dependências no host | Apenas Docker Desktop/Engine |
| Isolamento | Depende do ambiente do host | Ambiente isolado e reproduzível |
| Ollama | Instalado no host, acesso direto à GPU | Container próprio; GPU exige passthrough |
| Endereço do Ollama | `http://localhost:11434` | `http://ollama:11434` (ou `host.docker.internal`) |
| epubcheck/Java | Instalação manual e opcional | Já incluído na imagem do backend |
| Dados | Pastas locais (`backend/uploads`, `outputs`, `data`...) | Mesmas pastas montadas como volumes |
| Atualizar código | `--reload` aplica na hora | Precisa rebuildar a imagem (`up -d --build`) |
| Consumo de recursos | Menor (sem camadas do Docker) | Maior (containers + volume de modelos) |
| Depuração | Logs diretos no terminal, debugger fácil | Logs via `docker compose logs`, acesso via `exec` |
| Portabilidade | Depende do SO/versões | Igual em qualquer máquina com Docker |
| Primeira execução | Rápida | Mais lenta (build da imagem) |

---

## Qual modo escolher?

**Use sem Docker quando:**

- Você vai **desenvolver/alterar** o código (o `--reload` acelera muito).
- Já tem **Ollama no host** e quer aproveitar a GPU sem configurar passthrough.
- Quer menos consumo de RAM/disco e logs diretos.
- É uso pessoal, em uma máquina só.

**Use com Docker quando:**

- Quer **reprodutibilidade**: mesma execução em qualquer máquina.
- Vai **disponibilizar/deployar** a aplicação para outra pessoa ou servidor.
- Não quer lidar com instalação de Python, Java e epubcheck.
- Quer o ambiente isolado do host.
- Tem Linux/NVIDIA e consegue configurar GPU no container.

**Resumo prático:** desenvolvimento e uso pessoal no Windows → **local**. Deploy, compartilhamento ou ambiente "limpo" → **Docker**.

---

## Dados persistidos

| Caminho | Conteúdo |
|---|---|
| `backend/uploads/` | EPUBs enviados |
| `backend/outputs/` | EPUBs traduzidos |
| `backend/tmp/` | Arquivos temporários |
| `backend/glossaries/` | Glossários |
| `backend/data/epub_translate.db` | Jobs, capítulos e blocos |
| volume `ollama_data` (Docker) | Modelos baixados no container |

A limpeza automática é configurável em `backend/.env`:

```env
UPLOAD_RETENTION_DAYS=7
OUTPUT_RETENTION_DAYS=7
PURGE_TRANSLATION_PAYLOAD=true
```

Use `0` para desativar a limpeza.

---

## API

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/upload` | Envia EPUB ou PDF e inicia a tradução |
| `GET` | `/api/status/{job_id}` | Status e progresso |
| `GET` | `/api/jobs` | Lista jobs |
| `POST` | `/api/jobs/{job_id}/resume` | Retoma um job |
| `POST` | `/api/jobs/{job_id}/pause` | Pausa um job em andamento |
| `POST` | `/api/jobs/{job_id}/cancel` | Cancela um job |
| `GET` | `/api/download/{filename}` | Baixa o EPUB traduzido |
| `GET` | `/api/glossaries` | Lista glossários |
| `POST` | `/api/glossaries` | Cria glossário |
| `GET` | `/api/health` | Health check |

---

## Glossário

Mantém consistência de nomes e termos técnicos:

```http
POST /api/glossaries
Content-Type: application/json

{
  "name": "fantasy",
  "entries": {
    "Warden": "Guardião",
    "Guild": "Guilda"
  }
}
```

---

## Validação com epubcheck

- **Docker:** já instalado na imagem do backend.
- **Local:** opcional.
  1. Baixe em https://github.com/w3c/epubcheck/releases
  2. Coloque o `epubcheck` no `PATH` ou em `C:/epubcheck/epubcheck.jar`
  3. Requer Java instalado

Sem epubcheck, a tradução funciona normalmente; apenas a validação final é ignorada.

---

## Solução de problemas

**`python` não executa / abre a Microsoft Store (Windows)**
Use o Python do venv (`.\backend\.venv\Scripts\python.exe` a partir da raiz, ou `.\.venv\Scripts\python.exe` dentro de `backend`) ou o launcher `py -3.12`.

**`Activate.ps1 não pode ser carregado` (política de execução)**
```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

**`Connection error` / tradução não inicia**
- Confirme que o Ollama está no ar: `http://localhost:11434/api/tags`.
- Confirme o nome exato do modelo: `ollama list`.
- No Docker, o Base URL deve ser `http://ollama:11434` (não `localhost`).

**`model not found`**
O modelo configurado não foi baixado. Rode `ollama pull <modelo>` (ou `docker exec -it epub-ollama ollama pull <modelo>`).

**Porta em uso**
Altere no `--port` do backend ou no mapeamento do Compose (ex.: `5501:80`, `8001:8000`).

**Job parado em "Traduzindo..." por vários minutos / erro 500 do Ollama**
Sintoma de geração em loop: o modelo continua gerando até estourar o contexto. Verifique em `TRANSLATION_NUM_PREDICT` (use `2048`, nunca `-1`) e mantenha `TRANSLATION_REPEAT_PENALTY` em `1.15`. Depois reinicie o backend e clique em **Retomar**.

**Job parado com "Nenhum bloco foi traduzido"**
Provedor inacessível ou resposta inválida. Verifique os logs do backend e clique em **Retomar**.

**EPUB gerado sem imagens/capa**
Já corrigido: o rebuilder copia todos os itens não-documento (imagens, capa, CSS, fontes) preservando o tipo de mídia.

**Tradução lenta**
- Normal em CPU. Cada lote depende do modelo.
- Reduza `CHUNK_SIZE` se houver estouro de contexto.
- Prefira modelos menores (`qwen2.5:3b-instruct`) em máquinas com pouca RAM.

---

## Limitações

- A qualidade da tradução varia conforme o modelo escolhido.
- Livros grandes podem levar horas (a retomada evita perder progresso).
- A chave de API não é persistida; informe novamente ao retomar um job.
- O pipeline executa um job por vez.
- Notas de rodapé e elementos muito específicos ainda podem exigir revisão manual.
- Em PDFs, a ordem dos parágrafos depende do gerador do arquivo; tabelas, fórmulas, duas colunas e notas laterais podem sair fora de ordem.
- PDFs digitalizados (sem camada de texto) não são suportados; seria necessário OCR.
- O PDF de entrada não é preservado: a saída é sempre um EPUB.
- Aumente `MAX_UPLOAD_MB` no `backend/.env` se seus PDFs passarem de 50 MB.
