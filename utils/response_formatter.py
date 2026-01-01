def format_basic_opt_response(res: dict) -> str:
    return (
        f"Optimized Prompt:\n{res['optimized_prompt']}\n\n"
        f"Changes Made:\n{res['changes_made']}\n\n"
        f"Share Message:\n{res['share_message']}"
    )
    
def format_structure_opt_response(res: dict) -> str:
    return (
        f"Optimized Prompt:\n{res['optimized_prompt']}\n\n"
        f"Changes Made:\n{res['changes_made']}\n\n"
        f"Techniques Applied:\n{res['techniques_applied']}\n\n"
        f"Pro Tip:\n{res['pro_tip']}\n\n"
        f"Share Message:\n{res['share_message']}"
    )

def format_system_opt_response(res: dict) -> str:
    return (
        f"Optimized System Prompt:\n{res['system_prompt']}\n\n"
        f"Key Enhancements:\n{res['key_enhancements']}\n\n"
        f"Platform Tip:\n{res['platform_tip']}\n\n"
        f"Compliance Statement:\n{res['compliance_statement']}"
    )