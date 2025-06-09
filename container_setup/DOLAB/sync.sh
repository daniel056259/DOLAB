#!/bin/bash
# filepath: /root/sync.sh

CONFIG="/root/DOLAB/websocket_config.json"

MODEL_DIR=$(jq -r '.model_dir' "$CONFIG")
SOURCE_DIR=$(jq -r '.source_dir' "$CONFIG")
ARCHIVE_FORMAT=$(jq -r '.archive_format' "$CONFIG")
TIMESTAMP_FORMAT=$(jq -r '.timestamp_format' "$CONFIG")
SOCKET=$(jq -r '.socket' "$CONFIG")

# 모델 폴더를 압축해서 source_dir로 복사
MODEL_BASENAME=$(basename "$MODEL_DIR")
MODEL_TIMESTAMP=$(date +"$TIMESTAMP_FORMAT")
MODEL_ARCHIVE_NAME="${MODEL_BASENAME}_${MODEL_TIMESTAMP}.${ARCHIVE_FORMAT}"
MODEL_ARCHIVE_PATH="${SOURCE_DIR}/${MODEL_ARCHIVE_NAME}"

if [ "$ARCHIVE_FORMAT" = "tar.gz" ]; then
    tar -czf "$MODEL_ARCHIVE_PATH" -C "$(dirname "$MODEL_DIR")" "$MODEL_BASENAME"
elif [ "$ARCHIVE_FORMAT" = "zip" ]; then
    zip -r "$MODEL_ARCHIVE_PATH" "$MODEL_DIR"
else
    echo "지원하지 않는 압축 형식입니다: $ARCHIVE_FORMAT"
    exit 1
fi

echo "모델 압축 완료: $MODEL_ARCHIVE_PATH"

# WebSocket 서버에 sync 신호 전송 (Unix 도메인 소켓 사용)
echo "sync" | socat - UNIX-SENDTO:$SOCKET