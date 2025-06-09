import asyncio
import websockets
import subprocess
import json
import os

WEBSOCKET_CONFIG_PATH = "/root/DOLAB/websocket_config.json"
POD_INFO_PATH = "/root/DOLAB/pod_info.json"


def run_sync():
    try:
        with open(POD_INFO_PATH, "r", encoding="utf-8") as f:
            pod_info = json.load(f)
        with open(WEBSOCKET_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)

        source_dir = config["source_dir"]
        target_dir = config["target_dir"]

        ssh_opts = [
            "ssh",
            "-i", pod_info["identity_file"],
            "-p", str(pod_info["pod_ssh_port"]),
            "-o", "StrictHostKeyChecking=no"
        ]
        rsync_cmd = [
            "rsync", "-avz", "--delete",
            "-e", " ".join(ssh_opts),
            f'{pod_info["pod_user"]}@{pod_info["pod_ssh_public_ip"]}:{source_dir}',
            f"{target_dir}"
        ]
        result = subprocess.run(rsync_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print("sync 실패:", result.stderr)
            return False
        print("sync 완료:", result.stdout)
        return True
    except Exception as e:
        print("sync 예외:", e)
        return False


async def listen():
    with open(POD_INFO_PATH, "r", encoding="utf-8") as f:
        pod_info = json.load(f)
    uri = f'wss://{pod_info["pod_id"]}-8080.proxy.runpod.net/ws'
    async with websockets.connect(uri, ping_interval=None) as websocket:
        print("서버에 연결됨.")
        while True:
            message = await websocket.recv()
            print(f"수신 메시지: {message}")

            if message == "sync":
                await asyncio.to_thread(run_sync)
            elif message == "terminate":
                print("terminate 신호 수신: 마지막 sync 후 종료")
                run_sync()
                with open(POD_INFO_PATH, "r", encoding="utf-8") as f:
                    pod_info = json.load(f)
                import runpod
                runpod.api_key = pod_info["runpod_api_key"]
                runpod.terminate_pod(pod_id=pod_info["pod_id"])

                os.remove(POD_INFO_PATH)

                os._exit(0)

asyncio.run(listen())
