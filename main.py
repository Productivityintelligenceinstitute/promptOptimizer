from fastapi import FastAPI
from apis.routers.prompt_optimization import prompt_optimization_router
from apis.routers.accounts import accounts_router
from apis.routers.subscription import subscription_router
from apis.routers.chat import chat_router
from apis.routers.library import library_router
from apis.routers.customer_support_chatbot import customer_support_chatbot_router
from apis.routers.kb_ingestion import kb_ingestion_router
from admin.routes.permissions import permissioons_router
from admin.routes.packages import packages_router
from admin.routes.packages_permission import packages_permission_router
from middleware.cors import setup_cors
from fastapi_pagination import add_pagination

app = FastAPI(title="Jet Prompt Optimizer APIs")

setup_cors(app)
add_pagination(app)

app.include_router(customer_support_chatbot_router, tags=["Customer Support Chatbot"])
app.include_router(accounts_router, tags=["Accounts"])
app.include_router(subscription_router, tags=["Subscription"])
app.include_router(prompt_optimization_router, tags=["Prompt Optimization"])
app.include_router(chat_router, tags=["Chat"])
app.include_router(library_router, tags=["Library"])
app.include_router(kb_ingestion_router, tags=["Admin - KB Ingestion"])
app.include_router(permissioons_router, tags=["Admin - Permission Management"])
app.include_router(packages_router, tags=["Admin - Package Management"])
app.include_router(packages_permission_router, tags=["Admin - Package Permission Management"])