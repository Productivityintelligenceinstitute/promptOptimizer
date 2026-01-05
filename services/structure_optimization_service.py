from fastapi import HTTPException
from sqlalchemy.orm import Session

from permissions.access_control import validate_access

from core.exceptions.prompt_validation import PromptValidationException
from core.exceptions.llm import LLMServiceException

from llm.chains.chat_title_chain import build_chat_title_chain
from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository
from llm.chains.structured_optimization_chain import structured_optimization_chain

from utils.guardrails import validate_prompt
from utils.response_formatter import format_structure_opt_response

async def structured_level_optimization_service(payload, db: Session):
    try:
        user_id = payload.user_id
        
        validate_access(db, user_id, "STRUCT_OPT")
        
        chat_id = payload.chat_id
        if not chat_id:
            title_chain = build_chat_title_chain()
            title = title_chain.invoke({"user_prompt": payload.user_prompt})
            
            chat_id = ChatRepository.create_chat(db, user_id, title)
        
        try:
            validate_prompt(payload.user_prompt)
        except Exception:
            raise PromptValidationException("Prompt contains restricted content")
        
        MessageRepository.add_user_message(
            db=db,
            chat_id=chat_id,
            content=payload.user_prompt
        )
        
        try:
            chain = structured_optimization_chain()
            result = chain.invoke({"user_prompt": payload.user_prompt})
        except Exception:
            raise LLMServiceException("An error occurred during prompt optimization")
        
        llm_res_id = MessageRepository.add_llm_message(
            db=db,
            chat_id=chat_id,
            content=format_structure_opt_response(result)
        )
        
        return {
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": llm_res_id,
            "response": result
        }
    except Exception as e:
        raise HTTPException(detail=str(e), status_code=500)