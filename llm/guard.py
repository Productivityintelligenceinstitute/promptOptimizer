from langchain_openai import ChatOpenAI
from config import API_KEY, BASE_URL

def get_guard():
    return ChatOpenAI(
        base_url=BASE_URL,
        api_key=API_KEY,
        model= "openai/gpt-3.5-turbo"
    )
