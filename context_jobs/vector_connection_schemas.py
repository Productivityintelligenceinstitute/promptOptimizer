from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


_EMBEDDING_HELP = (
    "Vector DB settings plus embedding profile for query-time vectors. "
    "embedding_provider: openai | mistral | jina | cohere | voyage | google. "
    "embedding_model: model id for the chosen provider. "
    "embedding_api_key: required for mistral, jina, cohere, voyage. "
    "For openai/google: omit or leave empty to use Jet server keys (OPENAI_API_KEY / GOOGLE_API_KEY or GEMINI_API_KEY); "
    "set to use the customer's key. Jet does not supply platform keys for Cohere, Voyage, Mistral, or Jina. "
    "embedding_base_url: optional for openai (custom host); required semantics per provider docs. "
    "embedding_dimensions: optional int for OpenAI only (Matryoshka / reduced dims, e.g. 768 for Weaviate sandbox)."
)


class VectorConnectionCreate(BaseModel):
    name: str
    provider: str
    config: dict[str, Any] = Field(..., description=_EMBEDDING_HELP)
    status: str = "active"
    owner: Optional[str] = None

    class Config:
        json_schema_extra = {
            "examples": [
                {
                    "name": "Qdrant External KB",
                    "provider": "qdrant",
                    "config": {
                        "url": "https://your-cluster.cloud.qdrant.io",
                        "api_key": "qdrant_api_key",
                        "collection_name": "jet-context",
                        "embedding_model": "text-embedding-3-small",
                        "embedding_provider": "openai",
                    },
                    "status": "active",
                },
                {
                    "name": "Weaviate Cloud KB",
                    "provider": "weaviate",
                    "config": {
                        "deployment": "cloud",
                        "cluster_url": "https://YOUR-CLUSTER.weaviate.network",
                        "api_key": "weaviate_cloud_api_key",
                        "collection_name": "JetContextChunk",
                        "embedding_model": "text-embedding-3-small",
                        "embedding_provider": "openai",
                        "text_property": "text",
                    },
                    "status": "active",
                },
            ]
        }


class EmbeddingModelOption(BaseModel):
    """One selectable embedding model id for the Context Jobs UI."""

    model_id: str = Field(..., alias="modelId")
    provider: str
    default_dimensions: Optional[int] = Field(None, alias="defaultDimensions")

    class Config:
        populate_by_name = True


class VectorConnectionUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None
    status: Optional[str] = None


class VectorConnectionOut(BaseModel):
    id: UUID
    owner: str
    name: str
    provider: str
    status: str
    last_tested_at: Optional[datetime] = Field(None, alias="lastTestedAt")
    last_error: Optional[str] = Field(None, alias="lastError")
    created_at: datetime = Field(..., alias="createdAt")
    updated_at: datetime = Field(..., alias="updatedAt")

    class Config:
        from_attributes = True
        populate_by_name = True


class VectorConnectionTestResult(BaseModel):
    ok: bool
    provider: str
    message: str

