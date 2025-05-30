import asyncio
import websockets

class ChatServer:
    def __init__(self, host='localhost', port=8765):
        self.host = host
        self.port = port
        self.users = set()

    async def register(self, websocket):
        self.users.add(websocket)

    async def unregister(self, websocket):
        self.users.remove(websocket)

    async def handler(self, websocket):
        await self.register(websocket)
        try:
            async for message in websocket:
                await self.broadcast(message, sender=websocket)
        finally:
            await self.unregister(websocket)

    async def broadcast(self, message, sender=None):
        for user in self.users:
            if user != sender:
                await user.send(message)

    async def start(self):
        await websockets.serve(self.handler, self.host, self.port)
        print(f"Chat server started at ws://{self.host}:{self.port}")
        await asyncio.Future()

if __name__ == '__main__':
    server = ChatServer()
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("Server stopped.")

