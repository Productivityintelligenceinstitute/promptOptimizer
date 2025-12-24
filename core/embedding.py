from config import client, EMBED_MODEL

def embed_texts(texts, batch_size=32):
    all_embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        resp = client.embeddings.create(
            model=EMBED_MODEL,
            input=batch
        )
        all_embeddings.extend(d.embedding for d in resp.data)
    return all_embeddings
