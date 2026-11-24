"""The verified member acting in the current request.

Bound once by ``get_tenant_context`` (an async dependency, so the value is visible
to the endpoint and everything it calls). Attribution writers (audit events, job
versions, publish history, run initiator) read it so the recorded actor is always
the authenticated person, never the workspace partition key or a client-supplied
string. Background workers have no bound actor and pass attribution explicitly.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RequestActor:
    firebase_uid: str
    workspace_id: str
    owner: str


_current: ContextVar[Optional[RequestActor]] = ContextVar("context_jobs_request_actor", default=None)


def bind_request_actor(actor: RequestActor) -> None:
    _current.set(actor)


def clear_request_actor() -> None:
    _current.set(None)


def current_request_actor() -> Optional[RequestActor]:
    return _current.get()


def acting_user(default: Optional[str]) -> Optional[str]:
    """Firebase UID of the person acting in this request, else ``default``."""
    actor = _current.get()
    return actor.firebase_uid if actor else default


def acting_workspace(default: Optional[str] = None) -> Optional[str]:
    actor = _current.get()
    return actor.workspace_id if actor else default
