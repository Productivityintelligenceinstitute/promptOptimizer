from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends
import utils.utils as utils
from validator import validator
from constants import prompts
from llm.chain_builder import build_basic_level_optimization_chain, build_structured_level_optimization_chain, build_system_level_optimization_chain
from workflow.workflow import workflow
from database import database
from sqlalchemy.orm import Session
from uuid import uuid4
from models.chat_model import ChatModel
from models.messages_model import MessagesModel

router = APIRouter()


@router.post("/basic-level-optimization")
async def optimize_basic_prompt(user_prompt: validator.Prompt, db: Session = Depends(database.get_db)):
    
    print("Received chat_id:", user_prompt.chat_id)
    
    try:
        if not user_prompt.chat_id:
            chat_id = str(uuid4())
            
            print(chat_id)
            
            new_chat = ChatModel(
                chat_id=chat_id,
                chat_title=user_prompt.user_prompt[:50]  # First 50 chars as title
            )
            db.add(new_chat)
            db.commit()
            db.refresh(new_chat)
        else:
            chat_id = user_prompt.chat_id
        
        guard_res = utils.prompt_input_checks(user_prompt.user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            try:
                chain = build_basic_level_optimization_chain()
                
                user_message = MessagesModel(
                    chat_id=chat_id,
                    role="user",
                    content=user_prompt.user_prompt
                )
                
                print("Storing user message in DB:", user_message.content)
                
                db.add(user_message)
                db.commit()
                db.refresh(user_message)
                
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to build the optimization chain. {str(e)}"
                )
            
            try:
                res = chain.invoke({"user_prompt": user_prompt.user_prompt})
                
                assistant_res = f"""
                    Optimized Prompt:\n {res['optimized_prompt']}\n\n
                    Changes made:\n {res['changes_made']} \n\n
                    Share message:\n {res['share_message']}"""
                
                assistant_message = MessagesModel(
                    chat_id=chat_id,
                    role="assistant",
                    content= assistant_res
                )
                
                print("Storing assistant message in DB:", assistant_message.content)

                db.add(assistant_message)
                db.commit()
                db.refresh(assistant_message)
                
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"An error occurred during prompt optimization. {str(e)}"
                )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error.{str(e)}"
        )
    
    return {"response": res, "chat_id": chat_id}


@router.post("/structured-level-optimization")
async def structured_level_optimization(user_prompt: validator.Prompt, db: Session = Depends(database.get_db)):
    try:
        if not user_prompt.chat_id:
            chat_id = str(uuid4())
            
            print(chat_id)
            
            new_chat = ChatModel(
                chat_id=chat_id,
                chat_title=user_prompt.user_prompt[:50]  # First 50 chars as title
            )
            db.add(new_chat)
            db.commit()
            db.refresh(new_chat)
        else:
            chat_id = user_prompt.chat_id

        guard_res = utils.prompt_input_checks(user_prompt.user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            try:
                chain = build_structured_level_optimization_chain()
                
                user_message = MessagesModel(
                    chat_id=chat_id,
                    role="user",
                    content=user_prompt.user_prompt
                )
                
                print("Storing user message in DB:", user_message.content)
                
                db.add(user_message)
                db.commit()
                db.refresh(user_message)

            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to build the optimization chain."
                )
            
            try:
                res = chain.invoke({"user_prompt": user_prompt.user_prompt})

                assistant_res = f"""
                    Optimized Prompt:\n {res['optimized_prompt']}\n\n
                    Changes made:\n {res['changes_made']} \n\n
                    Techniques Applied:\n {res['techniques_applied']} \n\n
                    Pro Tip:\n {res['pro_tip']} \n\n
                    Share message:\n {res['share_message']}"""
                
                assistant_message = MessagesModel(
                    chat_id=chat_id,
                    role="assistant",
                    content= assistant_res
                )
                
                print("Storing assistant message in DB:", assistant_message.content)

                db.add(assistant_message)
                db.commit()
                db.refresh(assistant_message)

            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"An error occurred during prompt optimization. {str(e)}"
                )    
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error."
        )
    
    return {"response": res, "chat_id": chat_id}


@router.post("/mastery-level-optimization")
async def mastery_level_optimization(user_input: validator.Prompt):
    try:
        guard_res = utils.prompt_input_checks(user_input.user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            
            # config = {'configurable': {'thread_id': thread_id}}
            response = workflow.invoke({
                        "messages": [ 
                            {"role": "system", "content": prompts.agent_system_prompt},
                            {"role": "user", "content": user_input.user_prompt}
                    ]
                },
                    config= {'configurable': {'thread_id': 1}}
            )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error.{e}"
        )
    
    return {"response": response['messages'][-1].content}

@router.post("/system-level-optimization")
async def system_level_optimization(user_prompt: validator.Prompt, db: Session = Depends(database.get_db)):
    try:
        if not user_prompt.chat_id:
            chat_id = str(uuid4())
            
            print(chat_id)
            
            new_chat = ChatModel(
                chat_id=chat_id,
                chat_title=user_prompt.user_prompt[:50]  # First 50 chars as title
            )
            db.add(new_chat)
            db.commit()
            db.refresh(new_chat)
        else:
            chat_id = user_prompt.chat_id

        guard_res = utils.prompt_input_checks(user_prompt.user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            try:
                chain = build_system_level_optimization_chain()

                user_message = MessagesModel(
                    chat_id=chat_id,
                    role="user",
                    content=user_prompt.user_prompt
                )
                
                print("Storing user message in DB:", user_message.content)
                
                db.add(user_message)
                db.commit()
                db.refresh(user_message)

            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to build the optimization chain."
                )
            
            try:
                res = chain.invoke({"user_prompt": user_prompt.user_prompt})

                assistant_res = f"""
                    System Prompt:\n {res['system_prompt']}\n\n
                    Key Enhancements:\n {res['key_enhancements']} \n\n
                    Platform Tip:\n {res['platform_tip']} \n\n
                    Compliance Statement:\n {res['compliance_statement']}"""
                
                assistant_message = MessagesModel(
                    chat_id=chat_id,
                    role="assistant",
                    content= assistant_res
                )
                
                print("Storing assistant message in DB:", assistant_message.content)

                db.add(assistant_message)
                db.commit()
                db.refresh(assistant_message)

            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"An error occurred during prompt optimization. {str(e)}"
                )    
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal Server Error."
        )
    
    return {"response": res, "chat_id": chat_id}
