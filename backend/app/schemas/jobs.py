from pydantic import BaseModel
from typing import Optional


class TranslateRequest(BaseModel):
    job_id: str
    provider: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None


class JobStatus(BaseModel):
    job_id: str
    status: str  # queued, extracting, translating, rebuilding, validating, done, error, paused, cancelled
    progress: int = 0
    message: Optional[str] = None
    download_url: Optional[str] = None
    filename: Optional[str] = None
    total_chapters: int = 0
    done_chapters: int = 0
    total_blocks: int = 0
    done_blocks: int = 0
