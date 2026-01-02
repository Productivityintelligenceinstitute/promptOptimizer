from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import database
from models import models

from services.master_optimization_service import optimize_prompt_service

master_level_optimization_router = APIRouter(prefix="/master-level-optimization")

@master_level_optimization_router.post("")
async def mastery_level_optimization(payload: models.Prompt, db: Session = Depends(database.get_db)):
    return await optimize_prompt_service(payload, db)