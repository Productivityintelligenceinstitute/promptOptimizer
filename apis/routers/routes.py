from fastapi import APIRouter, HTTPException, status
from models.models import Prompt
from utils.validator import is_valid_len
from llm.chain_builder import build_guard_chain, build_schema_validation_chain, build_evaluation_engine_chain

router = APIRouter()

@router.post("/promptinput")
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
            detail="An error occurred while processing the prompt."
        )
        
    if guard_res["unsafe"]:
        
        print(guard_res)
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail="Your prompt was rejected because it contains unsafe, illegal, or sensitive information. Please revise your input and try again. "
        )
    
    if "PII" in guard_res["issues_detected"]:
        prompt.user_prompt = str(guard_res["redacted_prompt"])

    try:
        schema_validation_chain = build_schema_validation_chain()
    except Exception as e:
        raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to build the processing chain."
    )
    
    try:
        validation_res = schema_validation_chain.invoke({"user_prompt": prompt.user_prompt})
    except Exception as e:
        raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"An error occurred while processing the prompt. {str(e)}"
    )
    
    missing_values = [key for key, value in validation_res.items() if value == ""]
    
    print(missing_values)
    
    # Perform governance for entered missing values -> This logic will be implemented later
    # ---- START LOGIC ----
    # ---- END LOGIC ----
    
    try:
        evaluation_engine_chain = build_evaluation_engine_chain()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to build the processing chain."
        )
    
    try:
        evaluation_engine_res = evaluation_engine_chain.invoke({"user_prompt": prompt.user_prompt})
    except Exception as e:
        raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"An error occurred while processing the prompt. {str(e)}"
    )
    
    
    return {"validation_res": validation_res, "evaluation_engine_res": evaluation_engine_res}
    # return {"res": guard_res}

