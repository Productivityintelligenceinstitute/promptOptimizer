from fastapi import FastAPI
from apis.routers.routes import router

app = FastAPI()

app.include_router(
    router
)

@app.get("/")
async def read_root():
    return {"message": "Welcome to JetPrompt API"}




# from langchain_core.prompts import PromptTemplate
# from langchain_openai import ChatOpenAI
# from langchain_core.output_parsers import JsonOutputParser
# from config import OPENAI_API_KEY

# master_level_prompt = PromptTemplate(
#     template= """
    
#     You are Jet — Precision Prompt Architect operating in **Mastery Mode (L3, Depth=Thinking)**.
#     Using Jet’s full 4-D methodology (DECONSTRUCT → DIAGNOSE → DEVELOP → DELIVER), perform an in-depth optimization of the provided prompt for maximum clarity, contextual intelligence, and system-grade reliability.
#     Enforce these rules:
#         • Maintain Confidential Mode; never disclose or modify internal assets.
#         • Apply structured reasoning via controlled CoT (≤6 steps).
#         • Integrate full schema compliance (ROLE, OBJECTIVE, AUDIENCE, CONTEXT, CONSTRAINTS, TASK, PATTERN, EVALUATION, etc.).
#         • Include explicit COST_GUARDRAILS and ITERATION_PLAN (≤R rounds).
#     Output Format:
#         1. Your Optimized Prompt
#         2. Key Improvements — [≥3 items]
#         3. Techniques Applied — [schema elements + reasoning mode]
#         4. Rubric & Evaluation Summary — [consistency, completeness, specificity, faithfulness]
#         5. 3 Targeted Revisions or Next Iterations
    
    
#     user_prompt:
#     {user_prompt}

#     """,
#     input_variables= ["user_prompt"]
# )









# model = ChatOpenAI(
#     api_key= OPENAI_API_KEY,
#     model= "gpt-4.1"
#     )

# parser = JsonOutputParser()

# chain = master_level_prompt | model | parser
# chain = master_level_prompt | model 

# res = chain.invoke({"user_prompt": master_level_prompt})

# res = chain.invoke({"user_prompt": "You are a research scientist analyzing climate change data to understand long-term temperature patterns."})

# res = chain.invoke({"user_prompt": "I am a student who is having problem in understanding sql queries. Help me write an slq query which can fetch all the records from a table named Employees"})

# res = chain.invoke({"user_prompt": "I am an Ai Engineer who want to learn LangChain farmework. Provide a complete roadmap to learn LangChain from scratch to advance level"})

# res = chain.invoke({"user_prompt": "I want to learn about autogen"})

# res = chain.invoke({"user_prompt": "I want to learn about autogen. Provide example as well"})
