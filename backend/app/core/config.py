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
    translation_base_url: str = Field(default="http://ollama:11434")
    
    max_upload_mb: int = Field(default=50)
    chunk_size: int = Field(default=4000)
    enable_glossary: bool = Field(default=False)
    
    upload_dir: str = Field(default="./uploads")
    output_dir: str = Field(default="./outputs")
    temp_dir: str = Field(default="./tmp")
    
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
