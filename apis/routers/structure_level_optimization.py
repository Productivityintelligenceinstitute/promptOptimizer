from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import database
from models import models
from services.structure_optimization_service import optimize_prompt_service

structured_level_optimization_router = APIRouter(prefix="/structure-level-optimization")

@structured_level_optimization_router.post("")
async def structured_level_optimization(payload: models.Prompt, db: Session = Depends(database.get_db)):
    return await optimize_prompt_service(payload, db)