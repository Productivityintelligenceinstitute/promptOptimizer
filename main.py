from fastapi import FastAPI
from apis.routers.prompt_optimization import prompt_optimization_router
from apis.routers.accounts import accounts_router
from apis.routers.chat import chat_router
from apis.routers.customer_support_chatbot import customer_support_chatbot_router
from apis.routers.admin import kb_ingestion_router
from middleware.cors import setup_cors
from fastapi_pagination import add_pagination

app = FastAPI(title="Jet Prompt Optimizer APIs")

setup_cors(app)
add_pagination(app)

app.include_router(customer_support_chatbot_router, tags=["Customer Support Chatbot"])
app.include_router(accounts_router, tags=["Accounts"])
app.include_router(prompt_optimization_router, tags=["Prompt Optimization"])
app.include_router(chat_router, tags=["Chat"])
app.include_router(kb_ingestion_router, tags=["Admin - KB Ingestion"])