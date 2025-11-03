# from fastapi import FastAPI
# from apis.routers.routes import router

# app = FastAPI()

# app.include_router(
#     router
# )

# @app.get("/")
# async def read_root():
    
#     return {"message": "Welcome to JetPrompt API"}

from langchain_core.output_parsers import JsonOutputParser
from constants import prompts
from config import OPENAI_API_KEY
from langchain_openai import ChatOpenAI
from langchain_core.runnables import RunnablePassthrough, RunnableMap
import json


model = ChatOpenAI(
    model_name="gpt-4",
    openai_api_key=OPENAI_API_KEY
)

# clarify_chain = prompts.clarification_template | model | JsonOutputParser()
# # summarize_chain = prompts.summarization_template | model | JsonOutputParser()
# summary_chain = prompts.summary_prompt | model
# # final_chain = prompts.master_level_prompt2 | model | JsonOutputParser()




# response = clarify_chain.invoke({
#     "user_prompt": "Explain the theory of relativity in simple terms."})


# # print(response['clarification_questions'])

# # clarification_stage = response["clarification_questions"]
# # questions_list = clarification_stage.get("questions", [])

# for question in response["clarification_questions"]:
#     print(question)


# ans = input("Your answer: \n")

# summary_response = summary_chain.invoke({
#     "user_prompt": "Explain the theory of relativity in simple terms.",
#     "user_answers": ans
# })


# print("\n\nSummary Response: \n\n")
# print(summary_response)
# print(questions_list)



prompt = "Provide a simplified explanation of both the General and Special Theories of Relativity. This explanation should be aimed at an individual seeking to understand the topic for personal learning. There\'s no need to include the historical context or focus on any specific aspects of the theories."

# chain = prompts.master_level_prompt | model | JsonOutputParser()
chain = prompts.master_level_prompt | model
response3 = chain.invoke({
    "user_prompt": prompt
})

print("\n\nFinal Response: \n\n")
print(response3.content)

# questions = ''
# for qobj in questions_list:
#     # qobj is expected like {"q1": "Question text"}
#     if not isinstance(qobj, dict):
#         continue
#     # get first (and only) kv
#     k, v = next(iter(qobj.items()))
#     if (not v) or (str(v).strip() == ""):
#         # skip empty placeholders
#         continue
#     # ans = input(f"{v}\nYour answer: ").strip()
#     questions = questions + f"{v}\n"

# print("\nUser Answers Collected:")
# print(questions)

# ans = input()

# print(ans)

# qa_dict = {
#     "questions": questions,
#     "answers": ans
# }

# print(qa_dict)



# summarize_response = summarize_chain.invoke({
#     "clarification_questions_answers": json.dumps({"clarification_qa": qa_dict})})


# print(summarize_response)



# response3 = chain3.invoke({
#     "user_prompt": "Explain the theory of relativity in simple terms.", 
#     "clarification_responses": """
    
#     The user wants to include an explanation of both the Special and General Theories of Relativity. The information is intended for general educational use, aiming at fulfilling curiosity about physics in non-scientific people.The user is expecting a step-by-step breakdown supported by simple analogies. The content should be friendly, engaging, and slightly informal yet informative. Furthermore, the user prefers a moderate detail level to capture essential concepts without heavy math. The explanation should be written in simple, easy-to-understand language and should not exceed 400 words. A moderately detailed explanation is required. No browsing permissions were stipulated. No corresponding examples were noted. Please confirm if this summary correctly reflects your intent before optimization.

#     """
# })

# print(response3)


# Step 2: Combine them into one pipeline
# combined_chain = (
#     {
#         "user_prompt": RunnablePassthrough()
#     }
#     | RunnableMap({
#         # First, clarification output
#         "clarification_responses": clarify_chain,
#         "user_prompt": RunnablePassthrough()
#     })
#     | RunnableMap({
#         # Second, summarization output (takes clarification result)
#         "clarified_summary": summarize_chain,
#         "user_prompt": lambda x: x["user_prompt"],
#         "clarification_responses": lambda x: x["clarification_responses"]
#     })
#     | RunnableMap({
#         # Third, final generation (uses summary + original prompt)
#         "final_output": final_chain,
#         "user_prompt": lambda x: x["user_prompt"],
#         "clarification_responses": lambda x: x["clarified_summary"]
#     })
# )

# result = combined_chain.invoke("Explain the theory of relativity in simple terms.")
# print(result["final_output"])
