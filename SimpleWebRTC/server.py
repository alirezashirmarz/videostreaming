'''
Version: 1.2.0
Authors: @alirezashirmarz
email: ashirmarz@ufscar.br
Name: Signalling server (Simple WebRTC Setup)
'''
import asyncio, websockets

clients = set()

async def handler(ws):
    clients.add(ws)
    try:
        async for msg in ws:
            for c in clients:
                if c != ws:
                    await c.send(msg)
    finally:
        clients.remove(ws)

async def main():
    async with websockets.serve(handler, "127.0.0.1", 8765):
        print("Server started ws://127.0.0.1:8765")
        await asyncio.Future()

asyncio.run(main())