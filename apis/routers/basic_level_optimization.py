from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import database
from models import models
from services.basic_optimization_service import optimize_prompt_service

basic_level_optimization_router = APIRouter(prefix="/basic-level-optimization")

@basic_level_optimization_router.post("")
async def optimize_basic_prompt(user_input: models.Prompt, db: Session = Depends(database.get_db)):
    return await optimize_prompt_service(user_input, db)