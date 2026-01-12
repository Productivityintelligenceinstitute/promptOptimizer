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


@prompt_optimization_router.websocket("/ws/master-level-optimization")
async def master_level_optimization_ws(
    websocket: WebSocket, 
    db: Session = Depends(database.get_db)
):
    """
    WebSocket endpoint for master-level optimization with streaming support.
    
    This endpoint replaces the synchronous POST endpoint to prevent timeout issues.
    Tokens are streamed in real-time to the client, allowing for a responsive UX
    even during long-running operations.
    
    Expected payload format:
    {
        "user_id": "string",
        "user_prompt": "string",
        "chat_id": "string (optional)"
    }
    
    Event types sent to client:
    - chat_created: New chat was created
    - optimization_started: Optimization process started
    - token: Streaming token (includes token data and partial text)
    - model_start: LLM model started processing
    - model_end: LLM model finished processing
    - optimization_complete: Optimization completed successfully
    - error: An error occurred
    
    Client can send:
    - Standard payload: Start optimization
    - {"action": "stop"}: Cancel the operation
    """
    await websocket.accept()
    handler = WebSocketTokenHandler(websocket)
    
    try:
        while True:
            payload = await websocket.receive_json()
            
            if payload.get("action") == "stop":
                handler.cancel()
                await websocket.send_json({
                    "event": "cancelled",
                    "data": {"reason": "User requested cancellation"}
                })
                continue
            
            # Process the optimization request with streaming
            await master_level_optimization_service(
                websocket, 
                payload, 
                db, 
                handler
            )
    
    except WebSocketDisconnect:
        handler.cancel()
        print("Client disconnected from master-level-optimization — generation cancelled")
    except Exception as e:
        print(f"WebSocket error in master-level-optimization: {str(e)}")
        try:
            await websocket.send_json({
                "event": "error",
                "data": {"error": f"WebSocket error: {str(e)}"}
            })
        except:
            pass


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