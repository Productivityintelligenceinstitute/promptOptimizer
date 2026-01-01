from fastapi import HTTPException
import utils.utils as utils

def validate_prompt(prompt: str):
    res = utils.prompt_input_checks(prompt)
    if res["res"]["unsafe"]:
        raise HTTPException(status_code=400, detail="Unsafe prompt")
