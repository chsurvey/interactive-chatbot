import asyncio
import os
import sys
from typing import List, Dict

import websockets
from dotenv import load_dotenv
from openai import OpenAI  # openai >= 1.0.0

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
openai_client = OpenAI(api_key=openai_api_key)

class ChatClient:
    """Abstract WebSocket chat client base."""

    def __init__(self, uri: str):
        self.uri = uri

    async def connect(self):
        async with websockets.connect(self.uri) as ws:
            await asyncio.gather(self.send_loop(ws), self.recv_loop(ws))

    async def send_loop(self, ws):
        raise NotImplementedError

    async def recv_loop(self, ws):
        async for message in ws:
            await self.on_message(message, ws)

    async def on_message(self, message: str, ws):
        print(message)

    def run(self):
        try:
            asyncio.run(self.connect())
        except KeyboardInterrupt:
            print("Disconnected.")

class UserClient(ChatClient):
    """Interactive user client"""

    async def send_loop(self, ws):
        loop = asyncio.get_event_loop()
        while True:
            msg = await loop.run_in_executor(None, input, "You: ")
            await ws.send(msg)

    async def on_message(self, message: str, ws):
        print(f"Friend: {message}")

class GPTClient(ChatClient):
    """Background GPT bot using openai>=1.x SDK."""

    def __init__(self, uri: str, model: str = "gpt-3.5-turbo"):
        super().__init__(uri)
        self.model = model
        self.message_history: List[Dict[str, str]] = [
            {"role": "system", "content": "컴퓨터공학과 대학생 친구이다. 단답 위주의 20대 남성의 말투 소유."},
        ]

    async def send_loop(self, ws):
        # Bot doesn't initiate; just keep coroutine alive
        await asyncio.Future()

    async def on_message(self, message: str, ws):
        # Store user message
        self.message_history.append({"role": "user", "content": message})
        # Generate reply in executor to avoid blocking event loop
        loop = asyncio.get_event_loop()
        response: str = await loop.run_in_executor(None, self.generate_response)
        await ws.send(response)
        self.message_history.append({"role": "assistant", "content": response})

    def generate_response(self) -> str:
        try:
            completion = openai_client.chat.completions.create(
                model=self.model,
                messages=self.message_history,
                temperature=0.7,
                max_tokens=40,
            )
            reply: str = completion.choices[0].message.content.strip()
        except Exception as e:
            reply = f"[GPT error] {e}"
        return reply


def create_client(role: str, uri: str):
    if role == "user":
        return UserClient(uri)
    if role == "gpt":
        return GPTClient(uri)
    raise ValueError("role must be 'user' or 'gpt'")

if __name__ == "__main__":
    role = sys.argv[1] if len(sys.argv) > 1 else "user"
    create_client(role, "ws://localhost:8765").run()
