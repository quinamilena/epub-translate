from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List
import os


class Settings(BaseSettings):
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)
    cors_origins: str = Field(default="http://localhost:5500,http://127.0.0.1:5500")
    
    translation_provider: str = Field(default="ollama")
    translation_model: str = Field(default="translategemma:4b")
    translation_api_key: str = Field(default="")
    translation_base_url: str = Field(default="http://localhost:11434")
    # Janela de contexto e limite de tokens de saída enviados ao Ollama.
    # Sem num_ctx explícito o Ollama usa um valor baixo e trunca a resposta,
    # o que quebrava a segmentação de lotes grandes.
    translation_num_ctx: int = Field(default=8192)
    # Limite de tokens gerados por lote. Um valor infinito (-1) permite que
    # o modelo entre em repetição e gere até estourar o contexto, travando
    # o job por vários minutos. 2048 é folgado para lotes de CHUNK_SIZE.
    translation_num_predict: int = Field(default=2048)
    # Penalidade de repetição: reduz loops de geração em modelos menores.
    translation_repeat_penalty: float = Field(default=1.15)
    
    max_upload_mb: int = Field(default=50)
    chunk_size: int = Field(default=4000)
    enable_glossary: bool = Field(default=False)
    
    upload_dir: str = Field(default="./uploads")
    output_dir: str = Field(default="./outputs")
    temp_dir: str = Field(default="./tmp")
    
    # Retenção de arquivos (em dias). 0 desativa a limpeza automática.
    upload_retention_days: int = Field(default=7)
    output_retention_days: int = Field(default=7)

    # Banco de dados do pipeline por etapas
    database_path: str = Field(default="./data/epub_translate.db")
    purge_translation_payload: bool = Field(default=True)
    auto_resume_jobs: bool = Field(default=False)
    max_parallel_jobs: int = Field(default=1)
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
    
    def ensure_dirs(self):
        for d in [self.upload_dir, self.output_dir, self.temp_dir]:
            os.makedirs(d, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
