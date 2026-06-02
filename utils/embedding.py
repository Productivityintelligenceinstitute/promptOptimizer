from core.config import client, EMBED_MODEL

def embed_texts(texts, batch_size=32, model=None):
    embed_model = (model or "").strip() or EMBED_MODEL
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = client.embeddings.create(
            model=embed_model,
            input=batch
        )
        all_embeddings.extend(d.embedding for d in resp.data)
    return all_embeddings
