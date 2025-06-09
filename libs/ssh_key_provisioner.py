from .ssh_profile import SSHProfile
from .ssh_executor import SSHExecutor
from .logger import Log
import os
from pathlib import Path
import subprocess

class SSHKeyProvisioner:
    def __init__(self, key_name: str = "id_pod_sync", key_dir: str = "~/.ssh"):
        self.key_name = key_name
        self.key_dir = Path(os.path.expanduser(key_dir))
        self.private_key_path = self.key_dir / self.key_name
        self.public_key_path = self.key_dir / f"{self.key_name}.pub"

    def generate_keypair(self) -> tuple[str, str]:
        # 기존 키 파일이 있으면 삭제
        if self.private_key_path.exists(): self.private_key_path.unlink()
        if self.public_key_path.exists(): self.public_key_path.unlink()

        self.key_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ssh-keygen",
            "-t", "ed25519",
            "-f", str(self.private_key_path),
            "-N", "",
            "-C", "pod sync key"
        ]
        Log.v(f"키 생성: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            Log.e(f"[키 생성 실패] {result.stderr.strip()}")
            raise RuntimeError(f"SSH 키 생성 실패: {result.stderr.strip()}")

        Log.v(f"키 생성 완료: {self.private_key_path}")
        return str(self.private_key_path), str(self.public_key_path)

    def upload_public_key_to_pod(self, ssh_profile: SSHProfile, public_key_path: str | None = None) -> None:
        public_key_path = public_key_path or str(self.public_key_path)
        executor = SSHExecutor(ssh_profile)

        with open(public_key_path, "r", encoding="utf-8") as f:
            public_key = f.read().strip()

        remote_cmd = f"echo '{public_key}' >> ~/.ssh/authorized_keys"
        Log.v("pod에 공개키 추가 중...")
        executor.execute(remote_cmd, StrictHostKeyChecking=False)

    def upload_private_key_to_container(self, ssh_profile: SSHProfile, private_key_path: str | None = None) -> None:
        private_key_path = private_key_path or str(self.private_key_path)
        executor = SSHExecutor(profile=ssh_profile)

        remote_path = "~/.ssh"
        success = executor.upload_file(private_key_path, remote_path)
        if not success:
            Log.e("컨테이너로 개인키 업로드 실패")
            raise RuntimeError("컨테이너로 개인키 업로드 실패")

        # 권한 설정
        executor.execute(f"chmod 600 {remote_path}/*")
        Log.v("컨테이너에 개인키 전송 완료")
