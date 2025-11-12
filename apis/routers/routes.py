from fastapi import APIRouter, HTTPException, status
import utils.utils as utils
from llm.chain_builder import build_basic_level_optimization_chain, build_structured_level_optimization_chain, build_system_level_optimization_chain, build_schema_validation_chain, build_evaluation_engine_chain
from workflow.workflow import workflow
from langgraph.types import Command
from uuid import uuid4
from pydantic import BaseModel
from typing import Optional

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



@router.post("/get-clarification-questions")
async def clarification_questions(user_prompt: str):    
    try:
        guard_res = utils.prompt_input_checks(user_prompt)
        
        if not guard_res["res"]["unsafe"]:
            
            thread_id = str(uuid4())
            
            config = {'configurable': {'thread_id': thread_id}}
            
            initial_input = {'messages': [{"role": "user", "content": user_prompt}]}
            
            # try:
            res = workflow.invoke(initial_input, config)
            
            interrupt_data = res["__interrupt__"][0].value

            return {
                "message": interrupt_data["message"], 
                "clarification_questions": interrupt_data["clarification_questions"], 
                "thread_id": config['configurable']['thread_id']
            }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error.{e}"
        )



@router.post("/get-refined-prompt-summary")
async def refined_prompt_summary(user_answers: str, thread_id: str):    
    try:
        guard_res = utils.prompt_input_checks(user_answers)
        
        if not guard_res["res"]["unsafe"]:
            
            config = {'configurable': {'thread_id': thread_id}}
            
            res = workflow.invoke(
                Command(resume= user_answers),
                config   
            )
            
            print("\n\nResponse: \n\n")
            print(res)
            
            interrupt_data = res["__interrupt__"][0].value
            
            return {
                "instruction": interrupt_data["instruction"], 
                "summary": interrupt_data["summary"], 
                "thread_id": config['configurable']['thread_id']
            }
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error.{e}"
        )

@router.post("/mastery-level-optimization")
async def mastery_level_optimization(user_feedback: str, thread_id: str):    
    try:
        guard_res = utils.prompt_input_checks(user_feedback)
        
        if not guard_res["res"]["unsafe"]:
            
            config = {'configurable': {'thread_id': thread_id}}
            
            res = workflow.invoke(
                Command(resume= user_feedback),
                config   
            )
            
            print("\n\nResponse: \n\n")
            print(res)
        
        master_level_optimized_prompt = res.get("master_level_optimized_prompt", None)
        
        schema_validation = build_schema_validation_chain()
        schema_res = schema_validation.invoke({"user_prompt": master_level_optimized_prompt})
        
        for key, value in schema_res.items():
            if value in [None, "", []]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Schema Validation Error: {value['error_message']}"
                )
        
        evaluation_engine = build_evaluation_engine_chain()
        evaluation_res = evaluation_engine.invoke({"user_prompt": master_level_optimized_prompt})
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error.{e}"
        )
    
    return {"prompt":  schema_res,
            "scores": evaluation_res["scores"],
            "issues_found": evaluation_res["issues_found"],
            "suggestions": evaluation_res["suggestions"],
            "exemplar_rewrite": evaluation_res["exemplar_rewrite"]
        }

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
