from fastapi import APIRouter, HTTPException, status, Depends
import utils.utils as utils
from models import models
from constants import prompts
from llm.chain_builder import build_chat_title_generation_chain
from workflow.master_optimization import workflow
from database import database
from sqlalchemy import text
from sqlalchemy.orm import Session
from uuid import uuid4
from schemas.chat_model import ChatModel
from schemas.messages_model import MessagesModel
from schemas.subscription_model import SubscriptionsModel
from schemas.packages_model import PackagesModel
from database.db_utils import check_role, check_access, check_daily_usage, increment_daily_usage

master_level_optimization_router = APIRouter()

@master_level_optimization_router.post("/master-level-optimization")
async def mastery_level_optimization(user_input: models.Prompt, db: Session = Depends(database.get_db)):
    try:
        user_id = user_input.user_id
        
        role = check_role(
            db= db, 
            user_id= user_id
        )
        
        if role == "admin":
            if not user_input.chat_id:
                chat_id = str(uuid4())
                chat_title_chain = build_chat_title_generation_chain()
                chat_title = chat_title_chain.invoke({"user_prompt": user_input.user_prompt})
                
                new_chat = ChatModel(
                    chat_id=chat_id,
                    chat_title=chat_title,
                    user_id=user_id
                )
                db.add(new_chat)
                db.commit()
                db.refresh(new_chat)
            else:
                chat_id = user_input.chat_id

            guard_res = utils.prompt_input_checks(user_input.user_prompt)
            
            if not guard_res["res"]["unsafe"]:
                
                records = (
                    db.query(MessagesModel)
                    .filter(MessagesModel.chat_id == chat_id)
                    .order_by(MessagesModel.created_at.desc())
                    .limit(12)
                    .all()
                )[::-1]
                
                messages = []
                for record in records:
                    messages.append({
                        "role": record.role,
                        "content": record.content
                    })
                
                user_message = MessagesModel(
                    message_id= str(uuid4()),
                    chat_id=chat_id,
                    role="user",
                    content=user_input.user_prompt
                )
                db.add(user_message)
                db.commit()
                db.refresh(user_message)

                messages.append({
                    "role": "user",
                    "content": user_input.user_prompt
                })
                
                response = workflow.invoke({
                            "messages": [ 
                                {"role": "system", "content": prompts.agent_system_prompt},
                                *messages
                        ]
                    }
                )

                assistant_message = MessagesModel(
                    message_id= str(uuid4()),
                    chat_id=chat_id,
                    role="assistant",
                    content=response['messages'][-1].content
                )
                db.add(assistant_message)
                db.commit()
                db.refresh(assistant_message)
        else:
            package = (
                db.query(PackagesModel)
                .join(
                    SubscriptionsModel,
                    SubscriptionsModel.package_id == PackagesModel.package_id
                )
                .filter(
                    SubscriptionsModel.user_id == user_id,
                    SubscriptionsModel.status == "active"
                )
                .first()
            )
            
            if package.package_name != "free":
                subscription = (
                    db.query(SubscriptionsModel)
                    .filter(
                        SubscriptionsModel.user_id == user_id,
                        SubscriptionsModel.status == "active",
                        SubscriptionsModel.start_date <= text('now()'),
                        SubscriptionsModel.end_date >= text('now()')
                    )
                    .first()
                )
                if not subscription:
                    raise HTTPException(status_code=403, detail="No active subscription")

            access = check_access(
                db= db,
                user_id= user_id,
                permission_name= "MASTER_OPT"
            )

            if access and access.is_enabled:
                check_daily_usage(
                    db=db,
                    user_id=user_id,
                    permission_id=access.permission_id,
                    daily_limit=access.query_limit
                )
                            
                if not user_input.chat_id:
                    chat_id = str(uuid4())
                    chat_title_chain = build_chat_title_generation_chain()
                    chat_title = chat_title_chain.invoke({"user_prompt": user_input.user_prompt})
                    
                    new_chat = ChatModel(
                        chat_id=chat_id,
                        chat_title=chat_title,
                        user_id=user_id
                    )
                    db.add(new_chat)
                    db.commit()
                    db.refresh(new_chat)
                else:
                    chat_id = user_input.chat_id
                
                guard_res = utils.prompt_input_checks(user_input.user_prompt)
                
                if not guard_res["res"]["unsafe"]:
                    
                    records = (
                        db.query(MessagesModel)
                        .filter(MessagesModel.chat_id == chat_id)
                        .order_by(MessagesModel.created_at.desc())
                        .limit(12)
                        .all()
                    )[::-1]
                    
                    messages = []
                    for record in records:
                        messages.append({
                            "role": record.role,
                            "content": record.content
                        })
                    
                    user_message = MessagesModel(
                        message_id= str(uuid4()),
                        chat_id=chat_id,
                        role="user",
                        content=user_input.user_prompt
                    )
                    db.add(user_message)
                    db.commit()
                    db.refresh(user_message)

                    messages.append({
                        "role": "user",
                        "content": user_input.user_prompt
                    })
                    
                    response = workflow.invoke({
                                "messages": [ 
                                    {"role": "system", "content": prompts.agent_system_prompt},
                                    *messages
                            ]
                        }
                    )

                    assistant_message = MessagesModel(
                        message_id= str(uuid4()),
                        chat_id=chat_id,
                        role="assistant",
                        content=response['messages'][-1].content
                    )
                    db.add(assistant_message)
                    db.commit()
                    db.refresh(assistant_message)
                    
                    increment_daily_usage(
                        db=db,
                        user_id=user_id,
                        permission_id=access.permission_id
                    )
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User does not have access to Master Level Optimization."
                )
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error.{e}"
        )
    
    return {"user_id": user_id, "response": response['messages'][-1].content, "chat_id": chat_id}