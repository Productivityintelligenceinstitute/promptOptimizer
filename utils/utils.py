import tiktoken
from fastapi import HTTPException, status
from llm.chain_builder import build_guard_chain
from pwdlib import PasswordHash

def is_valid_len(prompt: str, limit: int = 5000):
    encoding = tiktoken.get_encoding("o200k_base")
    token_count = len(encoding.encode(prompt))

    return token_count < limit 


def prompt_input_checks(prompt):
    
    if not is_valid_len(prompt):
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
        guard_res = guard_chain.invoke({"user_prompt": prompt})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing the prompt. {str(e)}"
        )
        
    if guard_res["unsafe"]:
        raise HTTPException(
            status_code=status.HTTP_406_NOT_ACCEPTABLE,
            detail=f"The provided prompt contains unsafe or prohibited content. {guard_res}"
        )
        
    print("\n\nGuard Response: \n\n")
    print(guard_res)
    
    return {"res": guard_res}

password_hash = PasswordHash.recommended()

def verify_password(plain_password, hashed_password):
    return password_hash.verify(plain_password, hashed_password)

def get_password_hash(password):
    return password_hash.hash(password)
