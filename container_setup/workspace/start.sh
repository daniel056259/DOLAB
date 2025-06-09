#!/bin/bash

CONFIG="/root/DOLAB/websocket_config.json"

CLIENT_CONNECTED_SOCKET=$(jq -r '.client_connected_socket' "$CONFIG")
WEBSOCKET_SERVER_PATH=$(jq -r '.websocket_server_path' "$CONFIG")
MAIN_PATH=$(jq -r '.main_path' "$CONFIG")
rm -f $CLIENT_CONNECTED_SOCKET

# WebSocket 서버 시작 (백그라운드 실행)
echo "[1/3] WebSocket 서버 시작..."
python3 $WEBSOCKET_SERVER_PATH > server.log 2>&1 &
SERVER_PID=$!

# 클라이언트 연결 대기 (소켓 기반)
echo "[2/3] 클라이언트 연결 대기 중..."
signal=$(socat UNIX-RECVFROM:$CLIENT_CONNECTED_SOCKET STDOUT | head -n 1)
echo "클라이언트 연결됨: $signal"

# AI 학습 코드 실행
echo "[3/3] AI 학습 코드 실행..."
python3 $MAIN_PATH

# 종료 시 서버도 함께 종료
kill $SERVER_PID