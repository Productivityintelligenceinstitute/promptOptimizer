from database import database
from sqlalchemy import Column, Integer, String, TIMESTAMP
from sqlalchemy.sql import func


class ManagedJetKbNamespaceModel(database.Base):
    """Maps account owner id string → Pinecone namespace for managed Jet KB."""

    __tablename__ = "managed_jet_kb_namespaces"

    owner = Column(String, primary_key=True)
    namespace = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    # Set after a successful Use-with-demo-KB seed so later clicks skip re-ingest
    # (Jet KB is shared per owner; new jobs still retrieve the same vectors).
    demo_kb_seeded_at = Column(TIMESTAMP(timezone=True), nullable=True)
    # Bump when demo_kb_documents() gains files; stale owners get a delta ingest.
    demo_kb_bundle_version = Column(Integer, nullable=False, default=0, server_default="0")
