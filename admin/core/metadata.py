def infer_metadata(filename: str):
    name = filename.lower()
    meta = {"file": filename, "source": "Jet_KB"}

    if "blueprint" in name:
        meta["jet_layer"] = "jet_blueprint"
    elif "prompt" in name or "pe_" in name:
        meta["jet_layer"] = "prompt_engineering"
    elif "rag" in name:
        meta["jet_layer"] = "rag_methods"
    elif "agent" in name or "agentic" in name:
        meta["jet_layer"] = "agentic_ai"
    else:
        meta["jet_layer"] = "misc"

    return meta
