from langchain_core.output_parsers import JsonOutputParser
from constants import prompts
from llm.llm_models import get_guard_model, get_schema_validation_model

def build_guard_chain():
    guard = get_guard_model()
    parser = JsonOutputParser()
    return prompts.sanitization_prompt | guard | parser

def build_schema_validation_chain():
    schema_validator = get_schema_validation_model()
    parser = JsonOutputParser()
    return prompts.schema_validation_prompt | schema_validator | parser
