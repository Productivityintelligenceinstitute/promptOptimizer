import tiktoken
from fastapi import HTTPException, status
from llm.chain_builder import build_guard_chain
from pwdlib import PasswordHash
from config import client, index, EMBED_MODEL
from typing import List

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


def embed(text: str) -> List[float]:
    resp = client.embeddings.create(
        model=EMBED_MODEL,
        input=text
    )
    return resp.data[0].embedding


def retrieve(query: str, top_k: int = 8):
    q_emb = embed(query)
    res = index.query(
        vector=q_emb,
        top_k=top_k,
        include_metadata=True
    )
    return res.matches


def build_jet_system_prompt(mode: str) -> str:
    # keep it compact but on-brand
    return f"""
        You are Jet, a precision prompt architect and agentic assistant.
        Use the Jet knowledge base context I provide (prompt engineering, Jet schema, PhD DS blueprint).
        Follow the 4-D workflow:
        1) Deconstruct – restate the user's goal and constraints.
        2) Diagnose – identify missing info, relevant Jet patterns (CoT, few-shot, self-refine, etc.).
        3) Develop – propose a concrete solution (prompt, plan, or explanation) grounded in the context.
        4) Deliver – give a concise final answer formatted for a professional user.

        Mode = {mode}. In Quick mode be brief; in Mastery mode be more detailed and analytical.

        Cite retrieved snippets inline as [source:file:jet_layer] when relevant.
        If something is not supported by the context, say so explicitly instead of guessing.
    """.strip()
