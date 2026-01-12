import asyncio
import websockets
import json

async def test_ws():
    async with websockets.connect(
        "ws://localhost:8000/optimize-prompt/ws/basic-level-optimization",
        ping_interval=None  # prevent auto close
    ) as ws:
        await ws.send(json.dumps({
            "user_id": "23b7e1af-9da7-445b-8882-0c20b42c9373",
            "chat_id": None,
            "user_prompt": "I want to learn about AI."
        }))
        
        try:
            while True:
                msg = await ws.recv()
                print("Received:", msg)
        except websockets.ConnectionClosed:
            print("Connection closed by server")

asyncio.run(test_ws())
