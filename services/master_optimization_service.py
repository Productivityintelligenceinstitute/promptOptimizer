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
from llm.chains.master_optimization_chain import master_optimization_chain
from utils.guardrails import validate_prompt


async def master_level_optimization_service(websocket: WebSocket, payload: dict, db: Session,handler: WebSocketTokenHandler):
    try:
        user_id = payload.get("user_id")
        user_prompt = payload.get("user_prompt")
        chat_id = payload.get("chat_id")

        validate_access(db, user_id, "MASTER_OPT")
        
        if not chat_id:
            title_chain = build_chat_title_chain()
            chat_title = await run_in_threadpool(
                title_chain.invoke,
                {"user_prompt": user_prompt}
            )
            
            chat_id = ChatRepository.create_chat(db, user_id, chat_title)

        try:
            validate_prompt(user_prompt)
        except Exception:
            raise PromptValidationException("Prompt contains restricted content")
        
        
        MessageRepository.add_user_message(
            db=db,
            chat_id=chat_id,
            content=user_prompt
        )
        
        await websocket.send_json({"event": "processing"})
        
        chain = master_optimization_chain(handler= handler)
        
        await run_in_threadpool(
            chain.invoke,
            {"user_prompt": user_prompt}
        )
        
        llm_message_id = MessageRepository.add_llm_message(
            db=db,
            chat_id=chat_id,
            content=handler.final_text
        )
        
        await websocket.send_json({
            "event": "completed",
            "chat_id": str(chat_id),
            "message_id": str(llm_message_id),
            "prompt_type": "master"
        })

    except PromptValidationException as e:
        await websocket.send_json({"event": "error", "message": str(e)})

    except LLMServiceException as e:
        await websocket.send_json({"event": "error", "message": str(e)})

    except Exception as e:
        await websocket.send_json({
            "event": "error",
            "message": f"Internal server error occurred: {str(e)}"
        })
