import gc
import logging
import tracemalloc
import uuid
from pathlib import Path

from utils.reader import read_file
from utils.chunking import chunk_text
from utils.embedding import embed_texts
from utils.metadata import infer_metadata
from core.config import index
from core.ingestion_status import INGESTION_STATUS


CHUNK_EMBED_BATCH = 50


logger = logging.getLogger("kb_ingestion")
if not logger.handlers:
  handler = logging.StreamHandler()
  handler.setFormatter(
      logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
  )
  logger.addHandler(handler)
logger.setLevel(logging.INFO)


def _log_memory(stage: str) -> None:
  current, peak = tracemalloc.get_traced_memory()
  logger.info(
      "%s | Memory: current=%s KB, peak=%s KB",
      stage,
      current // 1024,
      peak // 1024,
  )


def ingest_job(job_id: str, filename: str, save_path: Path) -> None:
  tracemalloc.start()
  try:
    logger.info("Job %s: Starting ingestion for %s", job_id, filename)
    raw_text = read_file(save_path)
    _log_memory("After file read")

    if not raw_text.strip():
      INGESTION_STATUS[job_id]["status"] = "Failed: No text found"
      logger.error("Job %s: No text found in file", job_id)
      return

    chunks = chunk_text(raw_text)
    logger.info("Job %s: Chunked into %d chunks", job_id, len(chunks))
    _log_memory("After chunking")

    # Free raw text once chunked
    del raw_text
    gc.collect()

    meta_base = infer_metadata(filename)
    total_vectors = 0

    for i in range(0, len(chunks), CHUNK_EMBED_BATCH):
      batch_chunks = chunks[i : i + CHUNK_EMBED_BATCH]
      batch_embeddings = embed_texts(
          batch_chunks, batch_size=CHUNK_EMBED_BATCH
      )
      _log_memory(f"After embedding batch {i // CHUNK_EMBED_BATCH + 1}")

      vectors = []
      for chunk, emb in zip(batch_chunks, batch_embeddings):
        vectors.append(
            {
                "id": str(uuid.uuid4()),
                "values": emb,
                "metadata": {**meta_base, "preview": chunk[:300]},
            }
        )

      # Free embeddings as soon as they are converted to vectors
      del batch_embeddings
      gc.collect()

      index.upsert(vectors=vectors)
      total_vectors += len(vectors)
      logger.info(
          "Job %s: Upserted batch %d (%d vectors)",
          job_id,
          i // CHUNK_EMBED_BATCH + 1,
          len(vectors),
      )
      _log_memory(f"After upsert batch {i // CHUNK_EMBED_BATCH + 1}")

      del vectors
      del batch_chunks
      gc.collect()

    INGESTION_STATUS[job_id].update(
        {
            "file": filename,
            "chunks": len(chunks),
            "vectors": total_vectors,
            "status": "Ingested into Pinecone",
        }
    )
    logger.info("Job %s: Ingestion complete for %s", job_id, filename)

  except Exception as e:
    logger.exception("Job %s: Ingestion failed for %s", job_id, filename)
    INGESTION_STATUS[job_id]["status"] = f"Failed: {str(e)}"
  finally:
    tracemalloc.stop()
    gc.collect()

