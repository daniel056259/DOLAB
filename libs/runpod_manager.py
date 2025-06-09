from .runpod_profile import RunPodPort, RunPodProfile, GpuType
from .ssh_profile import SSHProfile
from .logger import Log
import runpod
from runpod.api.graphql import run_graphql_query
from runpod.error import QueryError
from typing import Any
from pathlib import Path
import json
import time
import os

class RunPodManager:
    def __init__(self, config_path: str = "./.config/.runpod_config.json"):
        self.config_path = Path(os.path.expanduser(config_path))
        self._load_config()

    def _load_config(self):
        if not self.config_path.exists():
            Log.w(f"설정 파일이 없어 기본 설정으로 새로 생성: {self.config_path}")
            self._create_config()

        with self.config_path.open("r", encoding="utf-8") as f:
            config = json.load(f)

        self.api_key = config.get("api_key")
        self.identity_file_path = os.path.expanduser(config.get("identity_file_path", "~/.ssh/id_ed25519"))
        self.jupyter_password = config.get("jupyter_password", "")

        if not self.api_key:
            Log.w(f"RunPod API 키가 등록되어 있지 않음. config_path: {self.config_path}")
            raise ValueError("RunPod API 키가 설정되어 있지 않습니다.")

        runpod.api_key = self.api_key
        Log.v("RunPodManager 설정 불러오기 완료")

    def _create_config(self):
        print("초기 설정이 필요합니다. 정보를 입력해주세요.")
        api_key = input("RunPod API Key: ").strip()
        identity = input("SSH 개인키 경로 (기본값: ~/.ssh/id_ed25519): ").strip() or "~/.ssh/id_ed25519"
        jupyter_pw = input("JupyterLab 비밀번호 (기본값: jupyterpassword): ").strip() or "jupyterpassword"

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        config = {
            "api_key": api_key,
            "identity_file_path": identity,
            "jupyter_password": jupyter_pw
        }
        with self.config_path.open("w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
        Log.i(f"설정 파일 생성됨: {self.config_path}")

    def create_pod(
        self, 
        name: str,
        image_name: str,
        gpu_type_id: str | list[str],
        cloud_type: str = "ALL",
        gpu_count: int = 1,
        container_disk_in_gb: int | None = None,
        ports: str = "22/tcp,8080/http",
        env: dict | None = None,
        start_jupyter: bool = False
    ) -> RunPodProfile: 
        
        Log.v(f"Pod 생성 요청: name={name}, image={image_name}, gpu_count={gpu_count}, disk={container_disk_in_gb}, ports={ports}")
        
        env_dict = dict(env) if env else {}
        if start_jupyter:
            env_dict["JUPYTER_PASSWORD"] = self.jupyter_password
            Log.v(f"env에 JUPYTER_PASSWORD 추가됨. env={env_dict}")
            if "8888/http" not in ports:
                ports += ",8888/http"
                Log.v(f"ports에 8888/http 추가됨. ports={ports}")

        if not isinstance(gpu_type_id, list) and gpu_type_id is not None:
            gpu_type_id = [gpu_type_id]

        for idx, current_gpu_id in enumerate(gpu_type_id):
            try:
                Log.i(f"[{idx+1}/{len(gpu_type_id)}] GPU ID {current_gpu_id}로 생성 시도 중...")
                pod = runpod.create_pod(
                    name=name,
                    image_name=image_name,
                    gpu_type_id=current_gpu_id,
                    cloud_type=cloud_type,
                    gpu_count=gpu_count,
                    container_disk_in_gb=container_disk_in_gb,
                    ports=ports,
                    env=env_dict
                )
                Log.i(f"Pod 생성 성공: pod_id={pod['id']}, gpu_id={current_gpu_id}")
                return self._wait_until_ready(pod_id=pod["id"])

            except QueryError as e:
                if "no longer any instances" in str(e):
                    Log.w(f"GPU 인스턴스 부족으로 생성 실패: gpu_type_id={current_gpu_id}")
                    continue
                raise  # 다른 오류는 그대로 발생
        
        Log.e("사용 가능한 GPU 인스턴스가 없어 Pod 생성 불가")
        raise RuntimeError("사용 가능한 GPU 인스턴스가 없어 Pod를 생성할 수 없습니다.")

    def get_pod_info(self, pod_id: str, suppress_log: bool = False) -> RunPodProfile: 
        runpod_profile = self.convert_to_runpod_profile(data=runpod.get_pod(pod_id=pod_id), suppress_log=suppress_log)
        return runpod_profile

    def get_pods(self) -> dict:
        return runpod.get_pods()

    def get_api_key(self) -> str:
        return self.api_key

    def terminate_pod(self, pod: str | RunPodProfile) -> None: 
        pod_id = pod if isinstance(pod, str) else pod["id"]
        Log.v(f"terminating pod: pod_id={pod_id}")
        runpod.terminate_pod(pod_id=pod_id)

    def _wait_until_ready(self, pod_id: str, timeout: int = 180, interval: int = 10) -> RunPodProfile: 
        """
        지정한 pod가 SSH 접속 가능한 상태가 될 때까지 대기

        :param pod_id: 대기할 pod ID
        :param timeout: 최대 대기 시간(초)
        :param interval: 확인 주기(초)
        :return: 준비 완료된 RunPodProfile
        :raises TimeoutError: 시간 초과 시 예외 발생
        """
        step_id = Log.start(f"Pod 준비 대기: pod_id={pod_id}, timeout={timeout}, interval={interval}")

        start_time = time.time()
        while time.time() - start_time < timeout:
            try: 
                profile = self.get_pod_info(pod_id=pod_id, suppress_log=True)
                Log.end(step_id=step_id)
                return profile
            except ValueError:
                Log.v(f"Pod 아직 준비되지 않음. {interval}초 이후 재시도...")
                time.sleep(interval)

        Log.end(step_id=step_id)
        Log.w(f"Pod 준비되지 않음 (timeout 초과)")
        raise TimeoutError(f"Pod가 준비되지 않았습니다. (pod_id={pod_id})")

    def convert_to_runpod_profile(self, data: dict[str, Any], suppress_log: bool = False) -> RunPodProfile:
        runtime = data.get("runtime", {})
        if not isinstance(runtime, dict): raise ValueError()
        runtime_ports = runtime.get("ports", [])

        # 포트 정보 파싱
        ports: list[RunPodPort] = []
        ssh_public_ip = ""
        ssh_port = -1
        jupyter_enabled = False

        for port_info in runtime_ports:
            port: RunPodPort = {
                "ip": port_info["ip"],
                "is_ip_public": port_info["isIpPublic"],
                "private_port": port_info["privatePort"],
                "public_port": port_info["publicPort"],
                "type": port_info["type"]
            }
            ports.append(port)

            # SSH 포트
            if port_info["privatePort"] == 22 and port_info["isIpPublic"]:
                ssh_public_ip = port_info["ip"]
                ssh_port = port_info["publicPort"]

            # Jupyter 확인
            if port_info["privatePort"] == 8888 and port_info["isIpPublic"]:
                jupyter_enabled = True


        if ssh_port == -1 or not ssh_public_ip:
            if not suppress_log: Log.w(f"유효한 SSH 포트 또는 IP를 추출 불가. data: {data}")
            raise ValueError("유효한 SSH 포트 또는 IP를 찾을 수 없습니다.")

        # SSH 프로필 구성
        ssh_profile: SSHProfile = {
            "host": data["name"],
            "hostname": ssh_public_ip,
            "port": str(ssh_port),
            "user": "root",
            "identity_file": self.identity_file_path,
        }

        return RunPodProfile(
            id=data["id"],
            name=data["name"],
            image_name=data["imageName"],
            desired_status=data["desiredStatus"],
            cost_per_hr=data["costPerHr"],
            gpu_count=data["gpuCount"],
            memory_in_gb=data["memoryInGb"],
            vcpu_count=data["vcpuCount"],
            container_disk_in_gb=data["containerDiskInGb"],
            machine_id=data["machineId"],
            gpu_display_name=data["machine"]["gpuDisplayName"],
            ports=ports,
            ssh_public_ip=ssh_public_ip,
            ssh_port=ssh_port,
            jupyter_enabled=jupyter_enabled,
            ssh_profile=ssh_profile
        )

    @staticmethod
    def get_gpus_detailed() -> list[GpuType]:
        QUERY_GPU_TYPES_DETAILED = """
query GpuTypes {
  gpuTypes {
    maxGpuCount
    id
    displayName
    memoryInGb
    secureCloud
    communityCloud
    securePrice
    communityPrice
  }
}
"""
        raw_response = run_graphql_query(QUERY_GPU_TYPES_DETAILED)
        cleaned_response = raw_response["data"]["gpuTypes"]
        gpu_types: list[GpuType] = []
        for gpu_info in cleaned_response:
            if "unknown" in gpu_info.get("id", "unknown").lower() or "unknown" in gpu_info.get("displayName", "unknown"): continue
            gpu_type: GpuType = {
                "maxGpuCount": gpu_info["maxGpuCount"],
                "id": gpu_info["id"],
                "displayName": gpu_info["displayName"],
                "memoryInGb": gpu_info["memoryInGb"],
                "secureCloud": gpu_info["secureCloud"],
                "communityCloud": gpu_info["communityCloud"],
                "securePrice": gpu_info["securePrice"],
                "communityPrice": gpu_info["communityPrice"]
            }
            gpu_types.append(gpu_type)
        return gpu_types