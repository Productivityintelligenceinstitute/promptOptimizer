from utils.embedding import embed_texts

def embed_chunks(chunks: list[str]) -> list[list[float]]:
    return embed_texts(chunks)
