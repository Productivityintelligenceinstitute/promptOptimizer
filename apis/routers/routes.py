from fastapi import APIRouter, HTTPException, status
from models.models import Prompt
import utils.utils as utils
from llm.chain_builder import build_basic_level_optimization_chain, build_structured_level_optimization_chain, build_system_level_optimization_chain
from workflow.workflow import workflow
from langgraph.types import Command

router = APIRouter()

@router.post("/basic-level-optimization")
async def optimize_basic_prompt(user_prompt: str):
    try:
        guard_res = utils.prompt_input_checks(user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            try:
                chain = build_basic_level_optimization_chain()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to build the optimization chain."
                )
            
            try:
                res = chain.invoke({"user_prompt": user_prompt})
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
async def structured_level_optimization(user_prompt: str):
    try:
        guard_res = utils.prompt_input_checks(user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            try:
                chain = build_structured_level_optimization_chain()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to build the optimization chain."
                )
            
            try:
                res = chain.invoke({"user_prompt": user_prompt})
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
async def mastery_level_optimization(user_prompt: str):    
    try:
        guard_res = utils.prompt_input_checks(user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            
            config = {'configurable': {'thread_id': 3}}
            
            try:
                res = workflow.invoke(
                    {'messages': [{"role": "user", "content": user_prompt}]},
                    config   
                )
                
                print("\n\nResponse After interrupt: \n\n")
                print(res)
            
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"An error occurred during prompt optimization. {str(e)}"
                )
            
            print("\n\n")
            user_answers = input("Please provide answers to the clarification questions: \n")
            
            try:
                res = workflow.invoke(Command(resume= user_answers), config)
                
                print("\n\nOutput After resuming: \n\n")
                print(res)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"An error occurred during prompt optimization. {str(e)}"
                )
            
            print("\n\n\n\n")
            user_feedback = input("Provide feedback on provided summary of your intent: \n")
            try:
                res = workflow.invoke(Command(resume= user_feedback), config)
                print("\n\nOutput After providing user feedback: \n\n")
                print(res)
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


@router.post("/system-level-optimization")
async def system_level_optimization(user_prompt: str):
    try:
        guard_res = utils.prompt_input_checks(user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            try:
                chain = build_system_level_optimization_chain()
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to build the optimization chain."
                )
            
            try:
                res = chain.invoke({"user_prompt": user_prompt})
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
