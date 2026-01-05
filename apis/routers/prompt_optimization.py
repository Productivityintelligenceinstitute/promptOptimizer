from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import database
from models import models

from services.basic_optimization_service import optimize_basic_prompt_service
from services.structure_optimization_service import structured_level_optimization_service
from services.master_optimization_service import master_level_optimization_service
from services.system_optimization_service import system_level_optimization_service


prompt_optimization_router = APIRouter(prefix="/optimize-prompt")


@prompt_optimization_router.post("/basic-level-optimization")
async def optimize_basic_prompt(payload: models.Prompt, db: Session = Depends(database.get_db)):
    return await optimize_basic_prompt_service(payload, db)


@prompt_optimization_router.post("/structure-level-optimization")
async def structured_level_optimization(payload: models.Prompt, db: Session = Depends(database.get_db)):
    return await structured_level_optimization_service(payload, db)


@prompt_optimization_router.post("/master-level-optimization")
async def master_level_optimization(payload: models.Prompt, db: Session = Depends(database.get_db)):
    return await master_level_optimization_service(payload, db)


@prompt_optimization_router.post("/system-level-optimization")
async def system_level_optimization(payload: models.Prompt, db: Session = Depends(database.get_db)):
    return await system_level_optimization_service(payload, db)