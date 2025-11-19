from fastapi import APIRouter, HTTPException, status
import utils.utils as utils
from models import models
from constants import prompts
from llm.chain_builder import build_basic_level_optimization_chain, build_structured_level_optimization_chain, build_system_level_optimization_chain
from workflow.workflow import workflow
from uuid import uuid4

router = APIRouter()


@router.post("/basic-level-optimization")
async def optimize_basic_prompt(user_prompt: models.Prompt):
    try:
        guard_res = utils.prompt_input_checks(user_prompt.user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            try:
                chain = build_basic_level_optimization_chain()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to build the optimization chain."
                )
            
            try:
                res = chain.invoke({"user_prompt": user_prompt.user_prompt})
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
    
    return {"response": res}


@router.post("/structured-level-optimization")
async def structured_level_optimization(user_prompt: models.Prompt):
    try:
        guard_res = utils.prompt_input_checks(user_prompt.user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            try:
                chain = build_structured_level_optimization_chain()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to build the optimization chain."
                )
            
            try:
                res = chain.invoke({"user_prompt": user_prompt.user_prompt})
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
    
    return {"response": res}


@router.post("/mastery-level-optimization")
async def mastery_level_optimization(user_input: models.Prompt):
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
async def system_level_optimization(user_prompt: models.Prompt):
    try:
        guard_res = utils.prompt_input_checks(user_prompt.user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            try:
                chain = build_system_level_optimization_chain()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to build the optimization chain."
                )
            
            try:
                res = chain.invoke({"user_prompt": user_prompt.user_prompt})
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
    
    return {"response": res}
