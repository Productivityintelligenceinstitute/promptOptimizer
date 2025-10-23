from langchain_core.output_parsers import JsonOutputParser
from constants import prompts
from llm.guard import get_guard

def build_chain():
    client = get_guard()
    parser = JsonOutputParser()
    return prompts.sanitization_prompt | client | parser
