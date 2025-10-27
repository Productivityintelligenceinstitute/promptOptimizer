# from llm.chain_builder import build_guard_chain, build_schema_validation_chain, build_evaluation_engine_chain

# def main():
# #     user_input = """
# # You are a research scientist analyzing climate change data to understand long-term temperature patterns.
# #     """

# #     user_input = """
# # You are a project manager at a software consultancy firm.
# # Your objective is to plan the release timeline for a new mobile application.
# # The schedule must not exceed six months and should account for two testing cycles.
# # Create a detailed project roadmap with milestones, team roles, and deadlines.
# #     """
    
# #     user_input = """
# # You are a data analyst working for a retail company.
# # Your goal is to identify purchasing trends from the last quarter’s sales data.
# # Do not include any customer personal information or store-specific identifiers in your analysis.
# # Prepare a concise summary highlighting the top-selling categories and emerging product patterns.
# #     """

#     # user_input = """
#     # The hospital board has been asking for better insight into how patient satisfaction correlates with staffing levels, but there isn’t a single system that tracks both. You’ve been looped into a meeting next week to show “some kind of overview” of what’s happening. The tricky part is that you can’t pull live data from the EHR due to privacy rules, and the nursing department hasn’t finalized their headcount reports yet. Whatever you come up with should help leadership understand trends without exposing any patient or employee identifiers.
#     # """
    
    
    
#     user_input = """
# A group of teachers wants to adopt AI tools to make grading faster, but the district superintendent is worried about bias and data privacy. They've asked you to prepare something that helps both sides see the pros and cons without taking a position yourself. The resources are limited, and there's no official budget for new software or workshops this semester. Try to make the output practical enough that the teachers can act on it right away if approved.
#     """


#     # schema_validation_chain = build_schema_validation_chain()
#     # guard_res = schema_validation_chain.invoke({"user_prompt": user_input})
    
    
#     evaluation_engine_chain = build_evaluation_engine_chain()
#     guard_res = evaluation_engine_chain.invoke({"user_prompt": user_input})

#     print("Guard Response:", guard_res)
    
# if __name__ == "__main__":
#     main()


from fastapi import FastAPI
from apis.routers.routes import router

app = FastAPI()

app.include_router(
    router
)

@app.get("/")
async def read_root():
    return {"message": "Welcome to JetPrompt API"}
