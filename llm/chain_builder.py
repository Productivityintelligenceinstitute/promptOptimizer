from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from constants import prompts
from llm.llm_models import get_guard_model, get_prompt_optimizer_model, get_schema_validation_model, get_evaluation_engine_model, get_chat_title_model

def build_guard_chain():
    guard = get_guard_model()
    parser = JsonOutputParser()
    return prompts.sanitization_prompt | guard | parser

def build_basic_level_optimization_chain(handler= None):
    optimizer = get_prompt_optimizer_model(handler)
    parser = JsonOutputParser()
    return prompts.basic_level_prompt | optimizer | parser

def build_structured_level_optimization_chain(handler= None):
    optimizer = get_prompt_optimizer_model(handler)
    parser = JsonOutputParser()
    return prompts.structured_level_prompt | optimizer | parser

def build_mastery_level_optimization_chain(handler= None):
    optimizer = get_prompt_optimizer_model(handler)
    parser = JsonOutputParser()
    return prompts.master_level_prompt | optimizer | parser

def build_schema_validation_chain():
    schema_validator = get_schema_validation_model()
    parser = JsonOutputParser()
    return prompts.schema_validation_prompt | schema_validator | parser

def build_evaluation_engine_chain():
    schema_validator = get_evaluation_engine_model()
    parser = JsonOutputParser()
    return prompts.evaluation_engine_prompt | schema_validator | parser

def build_system_level_optimization_chain(handler= None):
    optimizer = get_prompt_optimizer_model(handler)
    parser = JsonOutputParser()
    return prompts.system_level_prompt | optimizer | parser

def build_chat_title_generation_chain():
    chat_title_model = get_chat_title_model()
    parser = StrOutputParser()
    return prompts.chat_title_prompt | chat_title_model | parser