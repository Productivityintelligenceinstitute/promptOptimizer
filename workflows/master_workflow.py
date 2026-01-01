from llm.workflow.master_optimization import workflow

def run_workflow(system_prompt, history, user_prompt):
    messages = [
        {"role": "system", "content": system_prompt},
        *history,
        {"role": "user", "content": user_prompt}
    ]

    response = workflow.invoke({"messages": messages})
    return response["messages"][-1].content
