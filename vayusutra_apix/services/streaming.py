"""
VayuSutra APIx - Real-Time WebSockets & Server-Sent Events (SSE) Streaming Service
Broadcasts high-frequency tick updates, scrape telemetry, MAD filter rejections,
and inflation transmission alerts to connected central bank economists and dashboards.
"""

import asyncio
import collections
import datetime
import json
import logging
from typing import Dict, List, Any, Optional
from fastapi import WebSocket, WebSocketDisconnect

from .metrics import ACTIVE_WEBSOCKET_CLIENTS

logger = logging.getLogger("vayusutra.streaming")


class ConnectionManager:
    """
    Manages concurrent WebSocket subscriber connections with resilient heartbeat and broadcast queues.
    """

    def __init__(self, max_history_events: int = 100):
        self.active_connections: List[WebSocket] = []
        self._lock = asyncio.Lock()
        self.event_history: collections.deque = collections.deque(maxlen=max_history_events)

    async def connect(self, websocket: WebSocket) -> None:
        """Accepts and registers incoming client WebSocket."""
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)
            ACTIVE_WEBSOCKET_CLIENTS.set(len(self.active_connections))
        
        # Send recent events upon connection to populate client history
        try:
            for event in list(self.event_history)[-10:]:
                await websocket.send_text(json.dumps(event))
        except Exception as e:
            logger.debug(f"Error replaying event history: {e}")

    async def disconnect(self, websocket: WebSocket) -> None:
        """Removes disconnected WebSocket client."""
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)
            ACTIVE_WEBSOCKET_CLIENTS.set(len(self.active_connections))

    async def broadcast_event(self, event_type: str, data: Dict[str, Any], message: str = "") -> None:
        """
        Broadcasts a structured JSON event to all connected WebSocket subscribers.
        """
        event = {
            "event_type": event_type,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "message": message,
            "data": data,
        }
        self.event_history.append(event)

        async with self._lock:
            dead_connections = []
            for connection in self.active_connections:
                try:
                    await connection.send_text(json.dumps(event))
                except Exception as e:
                    logger.debug(f"Failed to send to client: {e}")
                    dead_connections.append(connection)

            for dead in dead_connections:
                if dead in self.active_connections:
                    self.active_connections.remove(dead)
            ACTIVE_WEBSOCKET_CLIENTS.set(len(self.active_connections))

    def get_recent_events(self, limit: int = 30) -> List[Dict[str, Any]]:
        """Retrieves recent broadcast events."""
        return list(self.event_history)[-limit:]


# Global singleton instance
stream_manager = ConnectionManager()
