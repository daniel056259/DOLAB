from .runpod_profile import RunPodProfile
from .ssh_executor import SSHExecutor
from .ssh_profile import SSHProfile
import tempfile
import json
import os

class PodInfoBuilder:
    @staticmethod
    def build(runpod_profile: RunPodProfile, runpod_api_key: str, identity_file_path: str) -> dict:
        return {
            "pod_id": runpod_profile["id"],
            "pod_ssh_public_ip": runpod_profile["ssh_profile"]["hostname"],
            "pod_user": runpod_profile["ssh_profile"]["user"],
            "pod_ssh_port": runpod_profile["ssh_profile"]["port"],
            "runpod_api_key": runpod_api_key,
            "identity_file": identity_file_path,
        }
    
class PodInfoUploader:
    @staticmethod
    def upload(info: dict, ssh_profile: SSHProfile, remote_path: str = "/root/DOLAB/pod_info.json") -> None:
        executor = SSHExecutor(profile=ssh_profile)
        with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
            json.dump(info, f, indent=2)
            tmp_path = f.name
        executor.upload_file(tmp_path, remote_path)
        os.remove(tmp_path)