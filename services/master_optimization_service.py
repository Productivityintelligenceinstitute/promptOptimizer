from sqlalchemy.orm import Session

from llm.chains.chat_title_chain import build_chat_title_chain
from permissions.access_control import validate_access

from core.exceptions.prompt_validation import PromptValidationException
from core.exceptions.llm import LLMServiceException

from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository

from workflows.master_workflow import run_workflow
from constants.prompts import agent_system_prompt

from utils.guardrails import validate_prompt

async def master_level_optimization_service(payload, db: Session):
    user_id = payload.user_id
    
    validate_access(db, user_id, "MASTER_OPT")
    
    chat_id = payload.chat_id
    if not chat_id:
        title_chain = build_chat_title_chain()
        chat_title = title_chain.invoke({"user_prompt": payload.user_prompt})
        
        chat_id = ChatRepository.create_chat(db, user_id, chat_title)
    
    try:
        validate_prompt(payload.user_prompt)
    except Exception:
        raise PromptValidationException("Prompt contains restricted content")
    
    history = MessageRepository.get_recent_messages(
        db, chat_id, limit=12
    )
    
    MessageRepository.add_user_message(
        db=db,
        chat_id=chat_id,
        content=payload.user_prompt
    )
    
    try:
        response = run_workflow(
            system_prompt=agent_system_prompt,
            history=history,
            user_prompt=payload.user_prompt
        )
    except Exception:
        raise LLMServiceException("An error occurred during prompt optimization")

    llm_res_id = MessageRepository.add_llm_message(
        db=db,
        chat_id=chat_id,
        content=response
    )
    
    return {
        "user_id": user_id,
        "chat_id": chat_id,
        "message_id": llm_res_id,
        "response": response
    }