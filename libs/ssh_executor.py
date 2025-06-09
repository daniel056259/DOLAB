from .logger import Log
from .ssh_profile import SSHProfile
from .ssh_result import SSHResult
import subprocess
import os


class SSHExecutor:
    def __init__(self, profile: SSHProfile):
        self.profile = profile


    def execute(self, command: str | list[str], log: bool = True, StrictHostKeyChecking: bool = True) -> SSHResult:
        user = self.profile["user"]
        hostname = self.profile["hostname"]
        port = self.profile["port"]
        identity = self.profile.get("identity_file")

        ssh_command = ["ssh", f"{user}@{hostname}", "-p", port]
        if identity:
            ssh_command += ["-i", identity]
        if not StrictHostKeyChecking:
            ssh_command += ["-o", "StrictHostKeyChecking=no"]

        # list[str]이면 ' && '로 연결하여 하나의 문자열 명령어로 변환
        if isinstance(command, list):
            joined_command = " && ".join(command)
        else:
            joined_command = command

        # 복잡한 명령어 실행 시 bash -c 사용 고려
        ssh_command += [joined_command]

        if log: Log.v(f"SSH 명령 실행: {' '.join(ssh_command)}")

        try:
            result = subprocess.run(ssh_command, capture_output=True, text=True)
        except Exception as e:
            if log: Log.e(f"SSH 명령 실행 실패 ({' '.join(ssh_command)}): {e}")
            raise RuntimeError(f"SSH 명령 실행 실패: {e}")

        ssh_result = self._build_result(result)

        if result.returncode != 0:
            if log: Log.w(f"[SSH 오류] {ssh_result}")
        else:
            if log: Log.i(f"[SSH 성공] {ssh_result['stdout']}")

        return ssh_result
    
    def upload_file(self, local_path: str, remote_path: str) -> bool:
        user = self.profile["user"]
        hostname = self.profile["hostname"]
        port = self.profile["port"]
        identity = self.profile.get("identity_file")

        if not os.path.exists(local_path):
            Log.e(f"로컬 파일이 존재하지 않음: {local_path}")
            raise FileNotFoundError(f"로컬 파일이 존재하지 않습니다: {local_path}")

        scp_command = ["scp", "-r", "-P", port]
        if identity:
            scp_command += ["-i", identity]

        scp_command += [local_path, f"{user}@{hostname}:{remote_path}"]

        Log.d(f"SCP 파일 전송: {' '.join(scp_command)}")

        try:
            result = subprocess.run(scp_command, capture_output=True, text=True)
        except Exception as e:
            Log.e(f"SCP 중 예외 발생: {e}")
            raise RuntimeError(f"SCP 실패: {e}")

        if result.returncode != 0:
            Log.w(f"[SCP 오류] {result.stderr.strip()}")
            return False

        Log.i(f"[SCP 성공] {local_path} → {remote_path}")

        # 업로드 후 원격 존재 확인
        if not self.exists(remote_path):
            Log.w(f"[SCP 후 확인 실패] 원격 파일 존재하지 않음: {remote_path}")
            return False
        
        return True

    def exists(self, remote_path: str) -> bool:
        test_command = f"test -e {remote_path}"

        try:
            result = self.execute(test_command)
        except Exception as e:
            Log.e(f"[존재 확인 실패] SSH 오류 또는 연결 실패: {e}")
            return False

        if result["returncode"] == 0:
            Log.i(f"[존재 확인] 원격 경로 존재: {remote_path}")
            return True
        else:
            Log.d(f"[존재 확인] 원격 경로 없음: {remote_path}")
            return False

    def _build_result(self, result: subprocess.CompletedProcess) -> SSHResult:
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }