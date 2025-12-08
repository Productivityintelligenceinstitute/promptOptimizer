from fastapi import FastAPI
from apis.routers.prompt_optimization import prompt_optimization_router
from apis.routers.accounts import accounts_router
from apis.routers.chat import chat_router
from apis.routers.customer_support_chatbot import customer_support_chatbot_router
from fastapi_pagination import add_pagination

app = FastAPI(title="Jet Prompt Optimizer APIs")

add_pagination(app)

app.include_router(customer_support_chatbot_router, tags=["Customer Support Chatbot"])
app.include_router(accounts_router, tags=["Accounts"])
app.include_router(prompt_optimization_router, tags=["Prompt Optimization"])
app.include_router(chat_router, tags=["Chat"])