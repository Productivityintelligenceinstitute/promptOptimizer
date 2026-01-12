from fastapi import WebSocket
from langchain_core.callbacks import AsyncCallbackHandler
from typing import Any, Dict, List

class WebSocketTokenHandler(AsyncCallbackHandler):
    def __init__(self, websocket: WebSocket):
        self.websocket = websocket
        self.final_text = ""
        self.cancelled = False

    async def on_chat_model_start(self, serialized: Dict[str, Any],messages: List[List[Any]],**kwargs: Any,) -> None:
        pass
    
    async def on_llm_new_token(self, token: str, **kwargs):
        if self.cancelled:
            raise Exception("Generation cancelled")
        self.final_text += token
        await self.websocket.send_json({
            "event": "token",
            "data": token
        })

    def cancel(self):
        self.cancelled = True

