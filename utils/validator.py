import tiktoken

def is_valid_len(prompt: str, limit: int = 5000):
    encoding = tiktoken.get_encoding("o200k_base")
    token_count = len(encoding.encode(prompt))

    return token_count < limit 
