from llm.workflow.master_optimization import workflow
from langchain_core.callbacks import BaseCallbackHandler

async def run_workflow_async(
    system_prompt, 
    history, 
    user_prompt, 
    handler: BaseCallbackHandler = None
):
    """
    Async version of run_workflow that supports streaming via callbacks.
    Allows token streaming to be sent to WebSocket clients in real-time.
    
    Args:
        system_prompt: System message for the LLM
        history: Conversation history
        user_prompt: User's prompt to optimize
        handler: AsyncCallbackHandler to handle streaming tokens
    
    Returns:
        The optimized prompt response
    """
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_prompt}
    ]
    
    callbacks = [handler] if handler else []
    
    # Invoke workflow with callbacks for streaming
    response = workflow.invoke(
        {"messages": messages},
        config={"callbacks": callbacks}
    )
    
    return response["messages"][-1].content
