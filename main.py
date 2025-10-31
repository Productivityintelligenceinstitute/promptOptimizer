from fastapi import FastAPI
from apis.routers.routes import router

app = FastAPI()

app.include_router(
    router
)

@app.get("/")
async def read_root():
    
    return {"message": "Welcome to JetPrompt API"}

