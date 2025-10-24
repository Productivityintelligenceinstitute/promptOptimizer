from llm.chain_builder import build_guard_chain, build_schema_validation_chain

def main():
#     user_input = """
# You are a research scientist analyzing climate change data to understand long-term temperature patterns.
#     """

    user_input = """
        How are you
    """


    schema_validation_chain = build_schema_validation_chain()
    guard_res = schema_validation_chain.invoke({"user_prompt": user_input})

    print("Guard Response:", guard_res)
    
if __name__ == "__main__":
    main()


# from fastapi import FastAPI
# from apis.routers.routes import router

# app = FastAPI()

# app.include_router(
#     router
# )

# @app.get("/")
# async def read_root():
#     return {"message": "Welcome to JetPrompt API"}
