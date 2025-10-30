from fastapi import APIRouter, HTTPException, status
from models.models import Prompt
from utils.validator import is_valid_len
from llm.chain_builder import build_guard_chain, build_basic_level_optimization_chain, build_structured_level_optimization_chain, build_mastery_level_optimization_chain

router = APIRouter()

@router.post("/prompt-input-checks")
async def prompt_input_checks(prompt: Prompt):
    if not prompt.user_prompt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both user prompt and target fields are required."
        )
    
    if not is_valid_len(prompt.user_prompt):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The entered prompt exceeds the maximum allowed length."
        )
    
    try:
        guard_chain = build_guard_chain()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build the processing chain."
        )
    
    try:
        guard_res = guard_chain.invoke({"user_prompt": prompt.user_prompt})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing the prompt. {str(e)}"
        )
        
    if guard_res["unsafe"]:
    
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="The provided prompt contains unsafe or prohibited content."
        )
    
    return {"res": guard_res}


@router.post("/basic-level-optimization")
async def optimize_basic_prompt(user_prompt: str):
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
        
    return {"response": res}


@router.post("/structured-level-optimization")
async def structured_level_optimization(user_prompt: str):
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

    return {"response": res}


@router.post("/mastery-level-optimization")
async def mastery_level_optimization(user_prompt: str):
    try:
        chain = build_mastery_level_optimization_chain()
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

    return {"response": res}