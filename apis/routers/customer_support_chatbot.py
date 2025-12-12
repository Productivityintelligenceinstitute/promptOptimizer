from typing import List
from fastapi import APIRouter
from validator.validator import JetRagRequest, JetRagResponse, JetContext
from config import client, GEN_MODEL
from utils.utils import retrieve, build_jet_system_prompt


customer_support_chatbot_router = APIRouter()


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
