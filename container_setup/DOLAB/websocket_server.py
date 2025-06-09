import asyncio
from websockets.asyncio.server import serve
import os
import socket
import json

WEBSOCKET_CONFIG_PATH = "/root/DOLAB/websocket_config.json"
with open(WEBSOCKET_CONFIG_PATH, "r", encoding="utf-8") as f:
    websocket_config = json.load(f)

connected_clients = set()


async def handler(connection):  # connection: ServerConnection
    connected_clients.add(connection)
    print("클라이언트 연결됨.")

    try:
        # 유닉스 소켓에 연결 신호 전송
        client_signal_sock = websocket_config["client_connected_socket"]
        try:
            if os.path.exists(client_signal_sock):
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
                    s.connect(client_signal_sock)
                    s.send(b"connected")
        except Exception as e:
            print(f"Unix 소켓 전송 오류: {e}")

        while True:
            message = await connection.recv()
            print("수신 메시지:", message)
    except Exception as e:
        print(f"예외 발생: {e}")
    finally:
        connected_clients.remove(connection)
        print("클라이언트 연결 종료")


async def unix_socket_listener(socket_path=websocket_config["socket"]):
    if os.path.exists(socket_path):
        os.remove(socket_path)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.bind(socket_path)
    sock.setblocking(False)
    loop = asyncio.get_running_loop()
    print(f"Unix 도메인 소켓 리스닝: {socket_path}")
    while True:
        try:
            data, _ = await loop.sock_recvfrom(sock, 1024)
            command = data.decode().strip()
            print(f"소켓 트리거 감지됨: {command}")
            for ws in connected_clients:
                await ws.send(command)
        except Exception:
            await asyncio.sleep(0.1)


async def main():
    server = await serve(handler, "0.0.0.0", 8080)  # type:ignore
    await asyncio.gather(
        server.wait_closed(),
        unix_socket_listener()
    )

asyncio.run(main())
