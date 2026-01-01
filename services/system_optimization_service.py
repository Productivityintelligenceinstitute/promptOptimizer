from fastapi import HTTPException, status

from sqlalchemy.orm import Session

from llm.chains.chat_title_chain import build_chat_title_chain
from llm.chains.system_optimization_chain import system_optimization_chain
from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository
from permissions.access_control import validate_access

from utils.guardrails import validate_prompt
from utils.response_formatter import format_system_opt_response

async def optimize_prompt_service(user_prompt, db: Session):
    try:
        user_id = user_prompt.user_id
        
        validate_access(db, user_id, "SYS_OPT")
        
        chat_id = user_prompt.chat_id
        if not chat_id:
            title_chain = build_chat_title_chain()
            chat_title = title_chain.invoke({"user_prompt": user_prompt.user_prompt})
            
            chat_id = ChatRepository.create_chat(db, user_id, chat_title)
            
        validate_prompt(user_prompt.user_prompt)
        
        MessageRepository.add_user_message(
            db=db,
            chat_id=chat_id,
            content=user_prompt.user_prompt
        )
        
        chain = system_optimization_chain()
        result = chain.invoke({"user_prompt": user_prompt.user_prompt})
        
        print("System Optimization Result:", result)

        llm_res_id = MessageRepository.add_llm_message(
            db=db,
            chat_id=chat_id,
            content=format_system_opt_response(result)
        )
        
        return {
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": llm_res_id,
            "response": result
        }
            
    except HTTPException:
        raise
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to optimize prompt{str(e)}"
        )