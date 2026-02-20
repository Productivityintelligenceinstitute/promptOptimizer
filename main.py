from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio
import logging
import sys

from apis.routers.prompt_optimization import prompt_optimization_router
from apis.routers.accounts import accounts_router
from apis.routers.subscription import subscription_router
from apis.routers.stripe import stripe_router
from apis.routers.chat import chat_router
from apis.routers.library import library_router
from apis.routers.customer_support_chatbot import customer_support_chatbot_router
from admin.routes.kb_ingestion import kb_ingestion_router

from admin.routes.permissions import permissioons_router
from admin.routes.packages import packages_router
from admin.routes.packages_permission import packages_permission_router
from admin.routes.update_role import update_role_router
from admin.routes.assign_package import assign_package_router
from admin.routes.users import users_admin_router

from middleware.cors import setup_cors
from fastapi_pagination import add_pagination

from database.database import create_db_tables
from background.tasks.user_cleanup import user_cleanup_loop
import schemas
import firebse.firebase_setup


def _setup_cleanup_logging():
    """Ensure user cleanup task logs appear on the server console."""
    log = logging.getLogger("background.tasks.user_cleanup")
    log.setLevel(logging.INFO)
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        log.addHandler(h)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure tables exist (for dev environments); production should rely on migrations.
    create_db_tables()

    _setup_cleanup_logging()
    # Start background user cleanup loop (soft deletes of long-expired, inactive users)
    asyncio.create_task(user_cleanup_loop())

    yield


app = FastAPI(title="Jet Prompt Optimizer APIs", lifespan=lifespan)

setup_cors(app)
add_pagination(app)

app.include_router(customer_support_chatbot_router, tags=["Customer Support Chatbot"])
app.include_router(accounts_router, tags=["Accounts"])
app.include_router(subscription_router, tags=["Subscription"])
app.include_router(stripe_router, prefix="/stripe", tags=["Stripe"])
app.include_router(prompt_optimization_router, tags=["Prompt Optimization"])
app.include_router(chat_router, tags=["Chat"])
app.include_router(library_router, tags=["Library"])
app.include_router(kb_ingestion_router, tags=["Admin - KB Ingestion"])
app.include_router(permissioons_router, tags=["Admin - Permission Management"])
app.include_router(packages_router, tags=["Admin - Package Management"])
app.include_router(packages_permission_router, tags=["Admin - Package Permission Management"])
app.include_router(update_role_router, tags=["Admin - Update User Role"])
app.include_router(assign_package_router, tags=["Admin - Assign Package"])
app.include_router(users_admin_router, tags=["Admin - Users"])