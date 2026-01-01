from fastapi import FastAPI
from contextlib import asynccontextmanager

from apis.routers.basic_level_optimization import basic_level_optimization_router
from apis.routers.structure_level_optimization import structured_level_optimization_router
from apis.routers.master_level_optimization import master_level_optimization_router
from apis.routers.system_level_optimization import system_level_optimization_router
from apis.routers.accounts import accounts_router
from apis.routers.subscription import subscription_router
from apis.routers.chat import chat_router
from apis.routers.library import library_router
from apis.routers.customer_support_chatbot import customer_support_chatbot_router
from apis.routers.kb_ingestion import kb_ingestion_router

from admin.routes.permissions import permissioons_router
from admin.routes.packages import packages_router
from admin.routes.packages_permission import packages_permission_router
from admin.routes.update_role import update_role_router

from middleware.cors import setup_cors
from fastapi_pagination import add_pagination

from database.database import create_db_tables
import schemas
import firebse.firebase_setup

@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_tables()
    yield

app = FastAPI(title="Jet Prompt Optimizer APIs", lifespan=lifespan)

setup_cors(app)
add_pagination(app)

app.include_router(customer_support_chatbot_router, tags=["Customer Support Chatbot"])
app.include_router(accounts_router, tags=["Accounts"])
app.include_router(subscription_router, tags=["Subscription"])
app.include_router(basic_level_optimization_router, tags=["Prompt Optimization"])
app.include_router(structured_level_optimization_router, tags=["Prompt Optimization"])
app.include_router(master_level_optimization_router, tags=["Prompt Optimization"])
app.include_router(system_level_optimization_router, tags=["Prompt Optimization"])
app.include_router(chat_router, tags=["Chat"])
app.include_router(library_router, tags=["Library"])
app.include_router(kb_ingestion_router, tags=["Admin - KB Ingestion"])
app.include_router(permissioons_router, tags=["Admin - Permission Management"])
app.include_router(packages_router, tags=["Admin - Package Management"])
app.include_router(packages_permission_router, tags=["Admin - Package Permission Management"])
app.include_router(update_role_router, tags=["Admin - Update User Role"])