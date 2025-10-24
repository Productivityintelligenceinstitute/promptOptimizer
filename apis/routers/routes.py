from fastapi import APIRouter, HTTPException, status
from models.models import Prompt
from utils.validator import is_valid_len
from llm.chain_builder import build_guard_chain

router = APIRouter()

@router.post("promptinput")
async def handle_prompt(prompt: Prompt):
    if not prompt.user_prompt or not prompt.target:
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
            detail=f"An error occurred while processing the prompt."
        )
        
    
    return {"response": guard_res}
