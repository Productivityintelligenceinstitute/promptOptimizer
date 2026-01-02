from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session

from database import database
from models import models

from services.system_optimization_service import optimize_prompt_service

system_level_optimization_router = APIRouter(prefix="/system-level-optimization")

@system_level_optimization_router.post("")
async def system_level_optimization(payload: models.Prompt, db: Session = Depends(database.get_db)):
    return await optimize_prompt_service(payload, db)
