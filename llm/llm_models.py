from langchain_openai import ChatOpenAI
from config import OPENAI_API_KEY

def get_guard_model():
    return ChatOpenAI(
        api_key= OPENAI_API_KEY,
        model= "gpt-3.5-turbo"
    )

def get_schema_validation_model():
    return ChatOpenAI(
        api_key= OPENAI_API_KEY,
        model= "gpt-4o-mini"
    )

def get_evaluation_engine_model():
    return ChatOpenAI(
        api_key= OPENAI_API_KEY,
        model= "gpt-4.1",
    )

def get_prompt_optimizer_model():
    return ChatOpenAI(
        api_key= OPENAI_API_KEY,
        model= "gpt-4.1",
        temperature=0.7
    )
