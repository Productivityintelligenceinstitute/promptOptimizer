from typing import Annotated
from typing_extensions import TypedDict
from constants import prompts
from llm.chain_builder import build_clarification_chain, build_refined_prompt_summary_chain, build_mastery_level_optimization_chain

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import interrupt

class State(TypedDict):
    user_prompt: str
    clarification_questions: dict
    user_answers: str
    clarification_summary: dict
    user_feedback: str
    master_level_optimized_prompt: str
    messages : Annotated[list, add_messages]

# create graph
graph = StateGraph(State)

# create graph nodes
def query_clarification(state: State) -> State:
    
    state["user_prompt"] = state["messages"][-1].content
    
    clarify_chain = build_clarification_chain()
    
    response = clarify_chain.invoke({
        "user_prompt": state["user_prompt"]})
    
    questions = response.get("clarification_questions", [])
    
    state["clarification_questions"] = questions
    
    questions_text = "\n".join(f"- {question}" for question in questions)
    
    state["messages"] = state["messages"] + [
        {"role": "assistant",  "content": f"Here are some clarification questions:\n{questions_text}"}
    ]
    
    print("\n\nClarification Questions: \n\n")
    print(questions_text)
    print("\n\n")
    
    user_answers = interrupt(
        {
            "clarification_questions": questions,
            "message": "Please answer the clarification questions:"
        }
    )
    
    print(f"\n\n User Answers: \n\n {user_answers}\n\n")
    
    state["user_answers"] = user_answers
    
    state["messages"] = state["messages"] + [
        {"role": "user", "content": f"Here are user answers for clarification questions:\n{user_answers}"}
    ]

    return state


def create_refined_prompt_summary(state: State):
    
    user_answers = state["user_answers"]
    
    print("\n\nUser Answers: \n\n")
    print(user_answers)
    
    summary_chain = build_refined_prompt_summary_chain()
    
    refined_prompt_summary = summary_chain.invoke({
        "user_prompt": state["user_prompt"],
        "user_answers": user_answers
    })
    
    print("\n\nRefined Prompt Summary: \n\n")
    print(refined_prompt_summary['clarified_summary'])
    
    state["clarification_summary"] = refined_prompt_summary
    
    state["messages"] = state["messages"] + [
        {"role": "assistant", "content": f"Thank you for your responses. Here is a summary based on your answers:\n{refined_prompt_summary}"}
    ]
    
    user_feedback = interrupt(
        {
            "instruction": "Please review the summary and provide any additional feedback or confirm if it's satisfactory.",
            "summary": refined_prompt_summary['clarified_summary']
        }
    )

    print(f"\n\n User Feedback: \n\n {user_feedback}\n\n")
    
    state["user_feedback"] = user_feedback
    
    state["messages"] = state["messages"] + [
        {"role": "user", "content": f"Here is user feedback for clarification summary:\n{user_feedback}"}
    ]
    
    return state


def gen_master_level_optimized_prompt(state: State):
    
    print(f'the new pompt is as follows \n\n{state["user_prompt"]}\n\n')
    
    
    prompt = state["clarification_summary"]['updated_prompt']
    
    final_chain = build_mastery_level_optimization_chain()
    
    master_prompt = final_chain.invoke({
        "user_prompt": prompt,
        "feedback": state["user_feedback"],
        "chat_history": state["messages"]
    })
    
    state["master_level_optimized_prompt"] = master_prompt
    
    state["messages"] = state["messages"] + [
        {"role": "assistant", "content": f"Here is the final master level optimized prompt:\n{master_prompt}"}
    ]
    
    return state

# add nodes
graph.add_node("query_clarification", query_clarification)
graph.add_node("clarification_summary", create_refined_prompt_summary)
graph.add_node("master_level_optimization", gen_master_level_optimized_prompt)

# add edges
graph.add_edge(START, "query_clarification")
graph.add_edge("query_clarification", "clarification_summary")
graph.add_edge("clarification_summary", "master_level_optimization")
graph.add_edge("master_level_optimization", END)

memory = MemorySaver()

workflow = graph.compile(checkpointer=memory)