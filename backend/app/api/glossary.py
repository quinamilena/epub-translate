from fastapi import APIRouter, HTTPException
from app.services.glossary_manager import GlossaryManager
from pydantic import BaseModel
from typing import Dict

router = APIRouter()
glossary_manager = GlossaryManager()


class GlossaryCreate(BaseModel):
    name: str
    entries: Dict[str, str]


@router.get("/glossaries")
def list_glossaries():
    return {"glossaries": glossary_manager.list_glossaries()}


@router.post("/glossaries")
def create_glossary(glossary: GlossaryCreate):
    path = glossary_manager.create_glossary(glossary.name, glossary.entries)
    return {"message": "Glossário criado", "path": path}


@router.get("/glossaries/{name}")
def get_glossary(name: str):
    entries = glossary_manager.load_glossary(name)
    return {"name": name, "entries": entries}
