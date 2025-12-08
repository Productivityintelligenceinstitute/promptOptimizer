# main.py
import os
from typing import List, Optional, Dict, Any

from fastapi import APIRouter
# from pydantic import BaseModel
# from dotenv import load_dotenv
# from langchain_openai import ChatOpenAI
# from pinecone import Pinecone

# from config import OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME
from validator.validator import JetRagRequest, JetRagResponse, JetContext
from utils.utils import retrieve, build_jet_system_prompt, GEN_MODEL, client

# load_dotenv()

# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
# PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

# client = ChatOpenAI(api_key=OPENAI_API_KEY)
# pc = Pinecone(api_key=PINECONE_API_KEY)
# index = pc.Index(PINECONE_INDEX_NAME)

# EMBED_MODEL = "text-embedding-3-large"
# GEN_MODEL = "gpt-4.1-mini"  # or gpt-4.1

customer_support_chatbot_router = APIRouter()


# class JetRagRequest(BaseModel):
#     query: str
#     mode: Optional[str] = "Structured"  # Quick | Structured | Mastery
#     top_k: int = 8


# class JetContext(BaseModel):
#     id: str
#     score: float
#     text_preview: str
#     metadata: Dict[str, Any]


# class JetRagResponse(BaseModel):
#     answer: str
#     contexts: List[JetContext]


# def embed(text: str) -> List[float]:
#     resp = client.embeddings.create(
#         model=EMBED_MODEL,
#         input=text
#     )
#     return resp.data[0].embedding


# def retrieve(query: str, top_k: int = 8):
#     q_emb = embed(query)
#     res = index.query(
#         vector=q_emb,
#         top_k=top_k,
#         include_metadata=True
#     )
#     return res.matches


# def build_jet_system_prompt(mode: str) -> str:
#     # keep it compact but on-brand
#     return f"""
# You are Jet, a precision prompt architect and agentic assistant.
# Use the Jet knowledge base context I provide (prompt engineering, Jet schema, PhD DS blueprint).
# Follow the 4-D workflow:
# 1) Deconstruct – restate the user's goal and constraints.
# 2) Diagnose – identify missing info, relevant Jet patterns (CoT, few-shot, self-refine, etc.).
# 3) Develop – propose a concrete solution (prompt, plan, or explanation) grounded in the context.
# 4) Deliver – give a concise final answer formatted for a professional user.

# Mode = {mode}. In Quick mode be brief; in Mastery mode be more detailed and analytical.

# Cite retrieved snippets inline as [source:file:jet_layer] when relevant.
# If something is not supported by the context, say so explicitly instead of guessing.
# """.strip()


@customer_support_chatbot_router.post("/jet/query", response_model=JetRagResponse)
async def jet_query(body: JetRagRequest):
    matches = retrieve(body.query, top_k=body.top_k)

    context_blocks = []
    contexts: List[JetContext] = []

    for m in matches:
        meta = m.metadata or {}
        preview = meta.get("preview", "")[:300]
        context_blocks.append(
            f"[source:{meta.get('file')} layer:{meta.get('jet_layer')}]\n{preview}"
        )
        contexts.append(
            JetContext(
                id=m.id,
                score=m.score,
                text_preview=preview,
                metadata=meta
            )
        )

    rag_context = "\n\n---\n\n".join(context_blocks) or "No context retrieved."
    system_prompt = build_jet_system_prompt(body.mode)

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"User query:\n{body.query}\n\n"
                f"Retrieved Jet KB context:\n{rag_context}\n\n"
                "Now respond following the 4-D workflow."
            ),
        },
    ]

    chat = client.chat.completions.create(
        model=GEN_MODEL,
        messages=messages,
        temperature=0.2,
    )

    answer = chat.choices[0].message.content
    return JetRagResponse(answer=answer, contexts=contexts)
