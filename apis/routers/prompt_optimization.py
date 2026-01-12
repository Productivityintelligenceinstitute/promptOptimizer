from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from database import database
from models import models

from llm.callbacks.websocket_token_handler import WebSocketTokenHandler

from services.basic_optimization_service import optimize_basic_prompt_service
from services.structure_optimization_service import structured_level_optimization_service
from services.master_optimization_service import master_level_optimization_service
from services.system_optimization_service import system_level_optimization_service

prompt_optimization_router = APIRouter(prefix="/optimize-prompt")


@prompt_optimization_router.websocket("/ws/basic-level-optimization")
async def optimize_basic_prompt(websocket: WebSocket, db: Session = Depends(database.get_db)):
    await websocket.accept()
    handler = WebSocketTokenHandler(websocket)
    
    try:
        while True:
            payload = await websocket.receive_json()
            
            if payload.get("action") == "stop":
                handler.cancel()
                await websocket.send_json({"event": "cancelled"})
                continue
            
            await optimize_basic_prompt_service(websocket, payload, db, handler)
    
    except WebSocketDisconnect:
        handler.cancel()
        print("Client disconnected — generation cancelled")


@prompt_optimization_router.websocket("/ws/structure-level-optimization")
async def structured_level_optimization(websocket: WebSocket, db: Session = Depends(database.get_db)):
    await websocket.accept()
    handler = WebSocketTokenHandler(websocket)
    
    try:
        while True:
            payload= await websocket.receive_json()
            
            if payload.get("action") == "stop":
                handler.cancel()
                await websocket.send_json({"event": "cancelled"})
                continue
            
            await structured_level_optimization_service(websocket, payload, db, handler)
    
    except WebSocketDisconnect:
        handler.cancel()
        print("Client disconnected — generation cancelled")


@prompt_optimization_router.post("/master-level-optimization")
async def master_level_optimization(payload: models.Prompt, db: Session = Depends(database.get_db)):
    return await master_level_optimization_service(payload, db)


@prompt_optimization_router.websocket("/ws/system-level-optimization")
async def system_level_optimization(websocket: WebSocket, db: Session = Depends(database.get_db)):
    await websocket.accept()
    handler = WebSocketTokenHandler(websocket)
    
    try:
        while True:
            payload= await websocket.receive_json()
            
            if payload.get("action") == "stop":
                handler.cancel()
                await websocket.send_json({"event": "cancelled"})
                continue
            
            await system_level_optimization_service(websocket, payload, db, handler)
    
    except WebSocketDisconnect:
        handler.cancel()
        print("Client disconnected — generation cancelled")