from pathlib import Path
from services.ingestion.ingestion_service import ingest_file_pipeline

def process_ingestion(file_path: Path, filename: str):
    try:
        ingest_file_pipeline(file_path, filename)
    except Exception as e:
        print(f"Error processing ingestion for {filename}")
