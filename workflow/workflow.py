from typing import Annotated
from typing_extensions import TypedDict

from llm.chain_builder import build_clarification_chain, build_refined_prompt_summary_chain, build_mastery_level_optimization_chain, build_schema_validation_chain, build_evaluation_engine_chain
from llm.llm_models import get_prompt_optimizer_model

from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langchain_core.tools import tool
from langgraph.prebuilt import ToolNode

from langgraph.checkpoint.memory import MemorySaver


model = get_prompt_optimizer_model()

class State(TypedDict):
    
    messages : Annotated[list, add_messages]

# create graph
graph = StateGraph(State)


# create tools for graph
@tool
def query_clarification(user_prompt: str):
    """
    Generate clarification questions on the basis of user's prompt to ensure understanding.
    """
    
    clarify_chain = build_clarification_chain()
    
    response = clarify_chain.invoke({"user_prompt": user_prompt})

    return response


@tool
def refined_prompt_summary_generation(user_prompt: str, user_answers: str):
    
    """
    Create a refined prompt and summary of user answers to clarification questions.
    """

    summary_chain = build_refined_prompt_summary_chain()
    
    refined_prompt_summary = summary_chain.invoke({
        "user_prompt": user_prompt,
        "user_answers": user_answers
    })
    
    return refined_prompt_summary


@tool
def master_level_prompt_generation(updated_prompt: str, user_feedback: str):
    
    """
    Generate a master level optimized prompt using the updated prompt, user feedback, and chat history.
    """    
    
    master_chain = build_mastery_level_optimization_chain()
    
    master_prompt = master_chain.invoke({
        "user_prompt": updated_prompt,
        "feedback": user_feedback
    })
    
    schema_validation = build_schema_validation_chain()
    schema_res = schema_validation.invoke({"user_prompt": master_prompt})
    
    evaluation_engine = build_evaluation_engine_chain()
    evaluation_res = evaluation_engine.invoke({"user_prompt": master_prompt})
    
    return {
        "master_prompt": schema_res,
        "evaluation": evaluation_res
    }

# binding tools
tools = [query_clarification, refined_prompt_summary_generation, master_level_prompt_generation]
llm_with_tools = model.bind_tools(tools)

# add nodes
def chat_node(state: State):
    """LLM node that uses provided tools to perform master level prompt optimization."""
    messages = state["messages"]
    response = llm_with_tools.invoke(messages)
    return {"messages": [response]}

tool_node = ToolNode(tools)

graph.add_node("chat_node", chat_node)
graph.add_node("tool_node", tool_node)

# add edges
def should_continue(state: State):
    """Determine if we should continue to tools or end."""
    messages = state["messages"]
    last_message = messages[-1]
    
    # If the last message has tool_calls, go to tools
    if hasattr(last_message, 'tool_calls') and last_message.tool_calls:
        return "tool_node"
    # Otherwise, end
    return END

graph.add_edge(START, "chat_node")
graph.add_conditional_edges("chat_node", should_continue)
graph.add_edge("tool_node", "chat_node")

memory = MemorySaver()

workflow = graph.compile(checkpointer=memory)