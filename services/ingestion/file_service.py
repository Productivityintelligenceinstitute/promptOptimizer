from pathlib import Path
from utils.reader import read_file

def read_text(file_path: Path) -> str:
    return read_file(file_path)
