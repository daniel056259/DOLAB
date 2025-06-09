from .logger import Log
from .ssh_profile import SSHProfile
from typing import List
from pathlib import Path
import subprocess


class SSHConfigManager:
    _config_file_path = Path("~/.ssh/config").expanduser()

    @classmethod
    def set_config_file_path(cls, path: str) -> None:
        cls._config_file_path = Path(path).expanduser()

    @classmethod
    def get_config_file_path(cls) -> Path:
        return cls._config_file_path

    @staticmethod
    def add_profile(profile: SSHProfile) -> bool: 
        host = profile['host']
        config_path = SSHConfigManager.get_config_file_path()

        # config 파일이 존재하지 않으면 생성
        if not config_path.exists():
            config_path.parent.mkdir(parents=True, exist_ok=True)
            config_path.touch()
            Log.i(f"SSH config 파일 생성됨: {config_path}")

        # 기존에 동일 Host가 있는지 확인
        with config_path.open("r", encoding="utf-8") as f:
            config_content = f.read()
            if f"Host {host}" in config_content:
                Log.w(f"이미 존재하는 SSH Host: {host}")
                raise ValueError(f"[error] 이미 존재하는 SSH Host: {host}")
            
        # 기존 fingerprint를 known_hosts에서 제거
        SSHConfigManager.remove_known_host(profile["hostname"], profile["port"])

        # SSH 프로필 포맷 구성
        lines = [
            f"Host {host}",
            f"    HostName {profile['hostname']}",
            f"    Port {profile['port']}",
            f"    User {profile['user']}",
        ]
        if profile.get("identity_file"):
            lines.append(f"    IdentityFile {profile['identity_file']}")

        entry_block = "\n".join(lines) + "\n"

        # config 파일에 append
        with config_path.open("a", encoding="utf-8") as f:
            f.write("\n" + entry_block)

        Log.i(f"SSH 프로필 추가됨: {host}")
        return True
    
    @staticmethod
    def remove_profile(profile: SSHProfile) -> bool: 
        host = profile["host"]
        config_path = SSHConfigManager.get_config_file_path()

        if not config_path.exists():
            Log.e(f"SSH config 파일이 존재하지 않음: {config_path}")
            raise FileNotFoundError(f"SSH config 파일이 존재하지 않습니다: {config_path}")

        # 기존 내용 읽기
        with config_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        # 해당 host 블록 추출
        new_lines: List[str] = []
        in_target_block = False
        removed = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Host "):
                if in_target_block:
                    in_target_block = False # 블록 종료
                    continue
                in_target_block = stripped == f"Host {host}"
                if in_target_block:
                    removed = True
                    continue  # "Host" 줄도 버림
            if not in_target_block:
                new_lines.append(line)

        if not removed:
            Log.w(f"SSH config에 host '{host}' 항목이 없음")
            raise ValueError(f"SSH config에 해당 host '{host}'를 찾을 수 없습니다.")
        
        # 불필요한 연속 빈 줄 제거
        cleaned_lines: List[str] = []
        prev_blank = False
        for line in new_lines:
            if line.strip() == "":
                if not prev_blank:
                    cleaned_lines.append(line)
                prev_blank = True
            else:
                cleaned_lines.append(line)
                prev_blank = False

        # 새 내용 덮어쓰기
        with config_path.open("w", encoding="utf-8") as f:
            f.writelines(cleaned_lines)

        # 기존 fingerprint를 known_hosts에서 제거
        SSHConfigManager.remove_known_host(profile["hostname"], profile["port"])

        Log.i(f"SSH 프로필 삭제됨: {host}")
        return True
    
    @staticmethod
    def read_profile(host: str) -> SSHProfile: 
        config_path = SSHConfigManager.get_config_file_path()

        if not config_path.exists():
            Log.e(f"SSH config 파일이 존재하지 않음: {config_path}")
            raise FileNotFoundError(f"SSH config 파일이 존재하지 않습니다: {config_path}")

        with config_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()

        in_target_block = False
        data: dict[str, str] = {}

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Host "):
                in_target_block = (stripped == f"Host {host}")
                continue

            if in_target_block:
                if stripped == "":
                    break  # 블록 종료
                key_value = stripped.split(None, 1)
                if len(key_value) == 2:
                    key, value = key_value
                    data[key.lower()] = value

        if not data:
            Log.w(f"SSH config에 host '{host}' 항목이 존재하지 않음")
            raise ValueError(f"SSH config에 host '{host}' 항목이 존재하지 않습니다.")

        required_keys = ["hostname", "port"]
        for key in required_keys:
            if key not in data:
                Log.e(f"{host} 항목에 '{key}'가 누락됨")
                raise ValueError(f"[error] '{host}' 항목에서 '{key}'가 누락됨")

        profile: SSHProfile = {
            "host": host,
            "hostname": data["hostname"],
            "port": data["port"],
            "user": data.get("user", "root"),
            "identity_file": data.get("identityfile", None),
        }

        Log.i(f"SSH 프로필 로드됨: {profile}")
        return profile
    
    @staticmethod
    def read_all_hosts() -> List[str]: 
        config_path = SSHConfigManager.get_config_file_path()

        if not config_path.exists():
            Log.e(f"SSH config 파일이 존재하지 않음: {config_path}")
            raise FileNotFoundError(f"SSH config 파일이 존재하지 않습니다: {config_path}")

        hosts: List[str] = []
        with config_path.open("r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("Host "):
                    parts = stripped.split()
                    if len(parts) == 2:
                        hosts.append(parts[1])  # Host 이름만 추출

        Log.i(f"발견된 SSH host 목록: {hosts}")
        return hosts

    @staticmethod
    def remove_known_host(ip: str, port: str) -> None:
        target = f"[{ip}]:{port}"
        try:
            subprocess.run(["ssh-keygen", "-R", target], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            Log.i(f"known_hosts에서 {target} 항목 제거 완료")
        except Exception as e:
            Log.w(f"known_hosts에서 {target} 항목 제거 실패: {e}")