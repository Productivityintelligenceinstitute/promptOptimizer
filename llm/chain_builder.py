from langchain_core.output_parsers import JsonOutputParser
from constants import prompts
from llm.llm_models import get_guard_model, get_prompt_optimizer_model

def build_guard_chain():
    guard = get_guard_model()
    parser = JsonOutputParser()
    return prompts.sanitization_prompt | guard | parser

# def build_schema_validation_chain():
#     schema_validator = get_schema_validation_model()
#     parser = JsonOutputParser()
#     return prompts.schema_validation_prompt | schema_validator | parser

# def build_evaluation_engine_chain():
#     schema_validator = get_evaluation_engine_model()
#     parser = JsonOutputParser()
#     return prompts.evaluation_engine_prompt | schema_validator | parser

def build_basic_level_optimization_chain():
    optimizer = get_prompt_optimizer_model()
    parser = JsonOutputParser()
    return prompts.basic_level_prompt | optimizer | parser

def build_structured_level_optimization_chain():
    optimizer = get_prompt_optimizer_model()
    parser = JsonOutputParser()
    return prompts.structured_level_prompt | optimizer | parser

def build_mastery_level_optimization_chain():
    optimizer = get_prompt_optimizer_model()
    parser = JsonOutputParser()
    return prompts.master_level_prompt | optimizer | parser

# def build_system_level_optimization_chain():
#     optimizer = get_prompt_optimizer_model()
#     parser = JsonOutputParser()
#     return prompts.system_level_prompt | optimizer | parser
