"""REST API and web dashboard."""

from mesh.api.app import create_app
from mesh.api.events import EventBus, event_bus

__all__ = ["create_app", "EventBus", "event_bus"]
