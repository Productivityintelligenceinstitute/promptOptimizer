from fastapi import WebSocket, HTTPException
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from llm.callbacks.websocket_token_handler import WebSocketTokenHandler
from permissions.access_control import validate_access
from core.exceptions.prompt_validation import PromptValidationException
from core.exceptions.llm import LLMServiceException
from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository
from llm.chains.chat_title_chain import build_chat_title_chain
from workflows.master_workflow import run_workflow_async
from constants.prompts import agent_system_prompt
from utils.guardrails import validate_prompt


async def master_level_optimization_service(
    websocket: WebSocket, 
    payload: dict, 
    db: Session,
    handler: WebSocketTokenHandler
):
    """
    WebSocket service for master-level optimization with streaming support.
    This handles token streaming to prevent timeout issues on long-running operations.
    """
    try:
        user_id = payload.get("user_id")
        user_prompt = payload.get("user_prompt")
        chat_id = payload.get("chat_id")
        
        # Validate user access
        try:
            validate_access(db, user_id, "MASTER_OPT")
        except Exception as e:
            await websocket.send_json({
                "event": "error",
                "data": f"Access validation failed: {str(e)}"
            })
            return
        
        # Create or use existing chat
        if not chat_id:
            try:
                title_chain = build_chat_title_chain()
                chat_title = await run_in_threadpool(
                    title_chain.invoke,
                    {"user_prompt": user_prompt}
                )
                
                chat_id = ChatRepository.create_chat(db, user_id, chat_title)
            except Exception as e:
                await websocket.send_json({
                    "event": "error",
                    "data": f"Failed to create chat: {str(e)}"
                })
                return
        
        # Validate prompt for restricted content
        try:
            validate_prompt(user_prompt)
        except Exception:
            await websocket.send_json({
                "event": "error",
                "data": "Prompt contains restricted content"
            })
            return
        
        # Retrieve conversation history
        try:
            history = MessageRepository.get_recent_messages(
                db, chat_id, limit=12
            )
        except Exception as e:
            await websocket.send_json({
                "event": "error",
                "data": f"Failed to retrieve chat history: {str(e)}"
            })
            return
        
        # Add user message to database
        try:
            MessageRepository.add_user_message(
                db=db,
                chat_id=chat_id,
                content=user_prompt
            )
        except Exception as e:
            await websocket.send_json({
                "event": "error",
                "data": f"Failed to save user message: {str(e)}"
            })
            return
        
        # Notify client that optimization is starting
        await websocket.send_json({
            "event": "optimization_started",
            "data": {"chat_id": str(chat_id)}
        })
        
        # Run the optimization workflow with streaming
        try:
            response = await run_workflow_async(
                system_prompt=agent_system_prompt,
                history=history,
                user_prompt=user_prompt,
                handler=handler
            )
        except Exception as e:
            await websocket.send_json({
                "event": "error",
                "data": f"Optimization failed: {str(e)}"
            })
            return
        
        # Save LLM response to database
        try:
            llm_res_id = MessageRepository.add_llm_message(
                db=db,
                chat_id=chat_id,
                content=response
            )
        except Exception as e:
            await websocket.send_json({
                "event": "error",
                "data": f"Failed to save response: {str(e)}"
            })
            return
        
        # Send completion event with metadata
        await websocket.send_json({
            "event": "optimization_complete",
            "data": {
                "user_id": user_id,
                "chat_id": str(chat_id),
                "message_id": str(llm_res_id)
            }
        })
        
    except Exception as e:
        await websocket.send_json({
            "event": "error",
            "data": f"Unexpected error: {str(e)}"
        })
