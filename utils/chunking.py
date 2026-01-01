def clean_text(text: str) -> str:
    text = text.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
    return ''.join(c for c in text if c.isprintable() or c in '\n\r\t')

def chunk_text(text: str, max_chars=1000, overlap=150):
    text = clean_text(text)

    MAX_SIZE = 5_000_000
    if len(text) > MAX_SIZE:
        text = text[:MAX_SIZE]

    chunks, start = [], 0
    MAX_CHUNKS = 5000

    while start < len(text) and len(chunks) < MAX_CHUNKS:
        end = min(len(text), start + max_chars)
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks
