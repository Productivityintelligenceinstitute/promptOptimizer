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
from llm.chain_builder import build_schema_validation_chain, build_evaluation_engine_chain



model = ChatOpenAI(
    model_name="gpt-4.1",
    openai_api_key=OPENAI_API_KEY
)

clarify_chain = prompts.clarification_template | model | JsonOutputParser()
summary_chain = prompts.summary_prompt | model | JsonOutputParser()
# # final_chain = prompts.master_level_prompt2 | model | JsonOutputParser()




response = clarify_chain.invoke({
    "user_prompt": "I want to learn unity game development"})


# print(response['clarification_questions'])

# clarification_stage = response["clarification_questions"]
# questions_list = clarification_stage.get("questions", [])

for question in response["clarification_questions"]:
    print(question)


ans = input("Your answer: \n")

summary_response = summary_chain.invoke({
    "user_prompt": "I want to learn unity game development",
    "user_answers": ans
})


print("\n\nSummary Response: \n\n")
print(summary_response)
# print(questions_list)



# prompt = "As a beginner in AI, I want to learn LangChain for my exams."

# # chain = prompts.master_level_prompt | model | JsonOutputParser()
# chain = prompts.master_level_prompt | model
# response3 = chain.invoke({
#     "user_prompt": prompt
# })

# print("\n\nFinal Response: \n\n")
# print(response3.content)


# schema_validation = build_schema_validation_chain()
# schema_res = schema_validation.invoke({"user_prompt": response3.content})


# print("\n\nSchema Validation Response: \n\n")
# print(schema_res)


# schema_res = {'role': '', 'objective': '', 'constraints': ['Beginner-friendly explanations (no prior experience assumed)', 'Step-by-step, clear, and concise instructions', 'Use simple analogies or examples where beneficial', 'Focus on key LangChain components relevant to exams', 'Maintain an encouraging, supportive tone', 'Avoid technical jargon unless explained', 'Respect academic integrity and do not assist in cheating'], 'task': 'introduce LangChain basics, break down essential concepts, provide exam-relevant examples, offer effective exam preparation tips, and suggest additional beginner resources'}

# print(json.dumps(schema_res))

# missing_field = [key for key in schema_res.keys() if schema_res[key] in ("", [], {})]


# print(missing_field)



# evaluation_chain = build_evaluation_engine_chain()
# evaluation_res = evaluation_chain.invoke({"user_prompt": json.dumps(schema_res)})

# print("\n\nEvaluation Response: \n\n")
# print(evaluation_res)




# evaluation_result = {
#     'scores': 
#         {
#             'clarity': [
#                 0.7, 
#                 'The prompt intent is generally understandable, but the lack of a clear, concise directive or main instruction makes it less immediately clear.'
#             ],
#             'completeness': [
#                 0.6, 
#                 'While constraints and desired outputs are present, the absence of context or a target audience (e.g., undergraduates, developers) means some critical information is missing.'
#             ],
#             'specificity': [
#                 0.7, 
#                 'Several specific instructions and constraints are listed, but the lack of explicit formatting or output guidelines leads to possible ambiguity in response structure.'
#             ], 
#             'faithfulness': [
#                 0.9, 
#                 'The prompt is consistent with its apparent educational and ethical intent, except for some vagueness regarding exam context and acceptable examples.'
#             ]
#         },
#         'issues_found': [
#             "No explicit instruction or directive summing up what the assistant should do (e.g., 'Write an introductory guide...').", 
#             'Missing context about the intended audience, learning objectives, or the nature of the exam (subject, format, exam level).',
#             'List of constraints is comprehensive but could be better organized and linked to defined outputs.',
#             'Lacks guidance on the format, depth, or length of the response.',
#             "'Exam-relevant examples' is vague; does not clarify what topics or question styles to target.",
#             "Faithfulness at risk due to insufficient definition of academic integrity boundaries (e.g., what constitutes 'assisting in cheating')."
#         ],
#         'suggestions': [
#             "Begin with a clear, directive statement outlining the assistant's main task (e.g., 'Write a beginner-friendly guide to LangChain for exam preparation...').", 
#             'Add context on the intended audience (e.g., undergraduate CS students, exam level).',
#             "Clarify what 'exam-relevant' means—specify the types of concepts or examples desired (e.g., short-answer, use-case scenarios).", 
#             'Define the preferred structure and depth of the output (e.g., sections for explanations, example questions, study tips, resources).',
#             'Explicitly reinforce academic integrity boundaries with a specific instruction about types of assistance to avoid.',
#             'Consolidate constraints into logically grouped categories for ease of application.'
#         ],
#         'exemplar_rewrite':
#             "Write a beginner-friendly guide introducing the fundamental concepts of LangChain, tailored for students preparing for academic exams (e.g., undergraduate computer science courses). Your response should:\n\n1. Clearly explain key LangChain components relevant to typical exam questions, assuming no prior experience.\n2. Provide step-by-step, concise explanations using simple analogies or examples where helpful.\n3. Include 'exam-relevant' sample questions or scenarios that assess understanding of these basics (focus on conceptual and practical applications, not direct answers).\n4. Offer effective preparation tips and recommend additional beginner-level resources for further study.\n5. Maintain an encouraging, supportive tone. Avoid technical jargon unless it is explained simply.\n6. Uphold academic integrity: do not provide direct solutions to exam questions or facilitate cheating in any way.\n\nStructure your response with clear sections for each of the above points."
# }



# print("\n\nEvaluation Result: \n\n")
# # print(evaluation_result['scores']['clarity'][1])
# print(evaluation_result['exemplar_rewrite'])




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
