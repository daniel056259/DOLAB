#!/bin/bash

CONFIG="/root/DOLAB/websocket_config.json"
SOCKET=$(jq -r '.socket' "$CONFIG")

echo "terminate" | socat - UNIX-SENDTO:$SOCKET