from fastapi import APIRouter, HTTPException, status
import utils.utils as utils
from llm.chain_builder import build_basic_level_optimization_chain, build_structured_level_optimization_chain, build_system_level_optimization_chain
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
# async def mastery_level_optimization(user_prompt: str):    
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
                # res = workflow.invoke(
                #     {'messages': [{"role": "user", "content": user_prompt}]},
                #     config   
                # )
                
                # print("\n\nResponse After interrupt: \n\n")
                # print(res)
            
            # except Exception as e:
            #     raise HTTPException(
            #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            #         detail=f"An error occurred during prompt optimization. {str(e)}"
            #     )
            
            # print("\n\n")
            # user_answers = input("Please provide answers to the clarification questions: \n")
            
            # try:
            #     res = workflow.invoke(Command(resume= user_answers), config)
                
            #     print("\n\nOutput After resuming: \n\n")
            #     print(res)
            # except Exception as e:
            #     raise HTTPException(
            #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            #         detail=f"An error occurred during prompt optimization. {str(e)}"
            #     )
            
            # print("\n\n\n\n")
            # user_feedback = input("Provide feedback on provided summary of your intent: \n")
            # try:
            #     res = workflow.invoke(Command(resume= user_feedback), config)
            #     print("\n\nOutput After providing user feedback: \n\n")
            #     print(res)
            # except Exception as e:
            #     raise HTTPException(
            #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            #         detail=f"An error occurred during prompt optimization. {str(e)}"
            #     )
    
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
    
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal Server Error.{e}"
        )
    
    return {"response": res.get("master_level_optimized_prompt", None)}

# @router.post("/mastery-level-optimization")
# async def mastery_level_optimization(user_prompt: str):    
#     try:
#         guard_res = utils.prompt_input_checks(user_prompt)
        
#         if not guard_res["res"]["unsafe"]:
            
#             thread_id = str(uuid4())
            
#             config = {'configurable': {'thread_id': thread_id}}
            
#             try:
#                 res = workflow.invoke(
#                     {'messages': [{"role": "user", "content": user_prompt}]},
#                     config   
#                 )
                
#                 print("\n\nResponse After interrupt: \n\n")
#                 print(res)
            
#             except Exception as e:
#                 raise HTTPException(
#                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                     detail=f"An error occurred during prompt optimization. {str(e)}"
#                 )
            
#             print("\n\n")
#             user_answers = input("Please provide answers to the clarification questions: \n")
            
#             try:
#                 res = workflow.invoke(Command(resume= user_answers), config)
                
#                 print("\n\nOutput After resuming: \n\n")
#                 print(res)
#             except Exception as e:
#                 raise HTTPException(
#                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                     detail=f"An error occurred during prompt optimization. {str(e)}"
#                 )
            
#             print("\n\n\n\n")
#             user_feedback = input("Provide feedback on provided summary of your intent: \n")
#             try:
#                 res = workflow.invoke(Command(resume= user_feedback), config)
#                 print("\n\nOutput After providing user feedback: \n\n")
#                 print(res)
#             except Exception as e:
#                 raise HTTPException(
#                     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#                     detail=f"An error occurred during prompt optimization. {str(e)}"
#                 )
    
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Internal Server Error."
#         )
    
#     return {"response": res}


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
