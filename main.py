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

# from fastapi import FastAPI
# from apis.routers.routes import router

# app = FastAPI()

# app.include_router(
#     router
# )

# @app.get("/")
# async def read_root():
    
#     return {"message": "Welcome to JetPrompt API"}





# Human in the Loop (HITL) Implementation

from config import OPENAI_API_KEY

from typing import Annotated
from typing_extensions import TypedDict
from constants import prompts
from llm.chain_builder import build_schema_validation_chain, build_evaluation_engine_chain

from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.tools import tool

from langgraph.prebuilt import ToolNode

from langgraph.types import Command, interrupt



# initialize the model
model = ChatOpenAI(
    model_name="gpt-4.1",
    openai_api_key=OPENAI_API_KEY
)

class State(TypedDict):
    user_prompt: str
    clarification_questions: dict
    clarification_answers: str
    summary: dict
    user_feedback: str
    final_output: str
    messages : Annotated[list, add_messages]

# create graph
graph = StateGraph(State)

def gen_clarification_ques(state: State) -> State:
    
    state["user_prompt"] = state["messages"][-1].content
    
    clarify_chain = prompts.clarification_template | model | JsonOutputParser()
    
    response = clarify_chain.invoke({
        "user_prompt": state["user_prompt"]})
    
    questions = response.get("clarification_questions", [])
    
    state["clarification_questions"] = questions
    
    questions_text = "\n".join(f"- {question}" for question in questions)
    
    state["messages"] = state["messages"] + [
                                                {
                                                    "role": "assistant",
                                                    "content": f"Here are some clarification questions:\n{questions_text}"
                                                }
                                            ]

    return state


def gen_clarification_response(state: State):
    
    user_answers = state["clarification_answers"]
    
    print("\n\nUser Answers: \n\n")
    print(user_answers)
    
    summary_chain = prompts.summary_prompt | model | JsonOutputParser()
    
    summary_response = summary_chain.invoke({
        "user_prompt": state["user_prompt"],
        "user_answers": user_answers
    })
    
    state["summary"] = summary_response
    
    state["messages"] = state["messages"] + [
                                                {
                                                    "role": "assistant",
                                                    "content": f"Thank you for your responses. Here is a summary based on your answers:\n{summary_response}"
                                                }
                                            ]
    
    return state


def gen_final_output(state: State):
    
    prompt = state["summary"]['updated_prompt']
    
    final_chain = prompts.master_level_prompt | model | StrOutputParser()
    
    final_response = final_chain.invoke({
        "user_prompt": prompt
    })
    
    state["final_output"] = final_response
    
    state["messages"] = state["messages"] + [
                                                {
                                                    "role": "assistant",
                                                    "content": f"Here is the final optimized prompt:\n{final_response}"
                                                }
                                            ]
    
    return state

# @tool
def human_interaction(state: State):
    # """Simulates human interaction for answering clarification questions"""
    
    # human_res = interrupt({'instruction': "Please answer the clarification questions", 'content': state["clarification_questions"]})
    
    human_res = interrupt({
        "instruction": "Please answer the following clarification questions:",
        "questions": state["clarification_questions"]
    })
    
    return {"clarification_answers": human_res}

def human_feedback(state: State):
    # """Simulates human interaction for answering clarification questions"""
    
    # human_res = interrupt({'instruction': "Please answer the clarification questions", 'content': state["clarification_questions"]})
    
    
    human_res = interrupt({
        "instruction": "Do you mean this",
        "questions": state["summary"]['clarified_summary']
    })
    
    return {"feedback": human_res}

# tools = [human_interaction]
# llm_with_tools = model.bind_tools(tools)

# add nodes
# graph.add_node("set_user_prompt", set_user_prompt)
graph.add_node("query_clarification", gen_clarification_ques)
graph.add_node("human_interaction", human_interaction)
graph.add_node("clarification_response", gen_clarification_response)
graph.add_node("human_feedback", human_feedback)
graph.add_node("final_output", gen_final_output)

# tool_node = ToolNode(tools= tools)
# graph.add_node("tools", tool_node)



# add edges
graph.add_edge(START, "query_clarification")
graph.add_edge("query_clarification", "human_interaction")
graph.add_edge("human_interaction", "clarification_response")
graph.add_edge("clarification_response", "human_feedback")
graph.add_edge("human_feedback", "final_output")
graph.add_edge("final_output", END)

memory = MemorySaver()

workflow = graph.compile(checkpointer=memory)

config = {'configurable': {'thread_id': 1}}

response = workflow.invoke(
    {'messages': [{"role": "user", "content": "I want to learn unity game development"}]},
    config   
)

print("\n\nOutput before interupt: \n\n")
print(response)


human_response = input("Your answer: \n")

human_input = Command(resume= human_response)

response = workflow.invoke(human_input, config)

print("\n\nOutput After interupt: \n\n")
print(response)


human_feedback = input("Your answer: \n")

human_input = Command(resume= human_feedback)

response = workflow.invoke(human_input, config)

print("\n\nOutput After interupt: \n\n")
print(response)


validation_chain = build_schema_validation_chain()
validation_chain_response = validation_chain.invoke({
    "user_prompt": response['final_output']
})

for key, value in validation_chain_response.items():
    if value in [None, "", []]:
        raise ValueError(f"Validation failed for {key}")

evaluation_chain = build_evaluation_engine_chain()
evaluation_chain_response = evaluation_chain.invoke({
    "user_prompt": response['final_output']
})


print("\n\nFinal Response: \n\n")

print(response['final_output'])
print("\n\n")
print(evaluation_chain_response)

