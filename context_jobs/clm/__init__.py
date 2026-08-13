"""CLM (Contract Lifecycle Management) connectors for Coupa and Ironclad."""

from context_jobs.clm.adapters import get_clm_adapter
from context_jobs.clm.url_parser import parse_clm_reference

__all__ = ["get_clm_adapter", "parse_clm_reference"]
