from fastapi import HTTPException, status

from sqlalchemy.orm import Session

from llm.chains.chat_title_chain import build_chat_title_chain
from permissions.access_control import validate_access
from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository

from workflows.master_workflow import run_workflow
from constants.prompts import agent_system_prompt

from utils.guardrails import validate_prompt

async def optimize_prompt_service(user_prompt, db: Session):
    try:
        user_id = user_prompt.user_id
        
        validate_access(db, user_id, "MASTER_OPT")
        
        chat_id = user_prompt.chat_id
        if not chat_id:
            title_chain = build_chat_title_chain()
            chat_title = title_chain.invoke({"user_prompt": user_prompt.user_prompt})
            
            chat_id = ChatRepository.create_chat(db, user_id, chat_title)
            
        validate_prompt(user_prompt.user_prompt)
        
        history = MessageRepository.get_recent_messages(
            db, chat_id, limit=12
        )
        
        MessageRepository.add_user_message(
            db=db,
            chat_id=chat_id,
            content=user_prompt.user_prompt
        )
        
        response = run_workflow(
            system_prompt=agent_system_prompt,
            history=history,
            user_prompt=user_prompt.user_prompt
        )

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
            
    except HTTPException:
        raise
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to optimize prompt"
        )