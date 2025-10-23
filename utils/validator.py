import re


def is_valid_len(prompt: str):
    cleaned_prompt = re.sub(r'\s+', ' ', prompt.strip())
    return False if len(cleaned_prompt) > 1000 else True