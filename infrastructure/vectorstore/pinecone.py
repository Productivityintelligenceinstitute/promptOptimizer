from core.config import index

BATCH_SIZE = 100

def upsert_vectors(vectors: list[dict]):
    for i in range(0, len(vectors), BATCH_SIZE):
        index.upsert(vectors=vectors[i:i + BATCH_SIZE])
