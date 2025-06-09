from .logger import Log
from .ssh_profile import SSHProfile
from .ssh_config_manager import SSHConfigManager
from .container_profile import ContainerProfile
from .ssh_result import SSHResult
from .ssh_executor import SSHExecutor
from typing import Literal
import time
import shlex
import re


class HostMachine:
    def __init__(self, ssh_profile: SSHProfile): 
        self.host_profile = ssh_profile
        self.executor = SSHExecutor(profile=self.host_profile)

    def create_container(
        self, 
        name: str, 
        image: str, 
        ports: list[tuple[str, str]], # [(host_port, container_port), ...]
        public_key_path: str, 
        private_key_path: str | None = None, 
        set_jupyter_lab: bool = False, 
        register_ssh: bool = False
    ) -> ContainerProfile: 
        Log.i(f"컨테이너 생성 시작: name={name}, image={image}, ports={ports}")

        # 이름 중복 확인
        if self.container_exists(name):
            Log.w(f"[{name}] 이미 존재하는 컨테이너 이름입니다.")
            raise RuntimeError(f"이미 존재하는 컨테이너 이름: {name}")
        
        # SSH 연결용 22번 포트 존재 확인
        ssh_port = next((host for host, cont in ports if cont == "22"), None)
        if not ssh_port:
            Log.w("SSH(22) 포트 바인딩을 찾지 못함")
            raise RuntimeError("SSH(22) 포트 바인딩이 필요합니다.")

        # 포트 중복 확인
        for host_port, _ in ports:
            if self._is_port_in_use(host_port):
                Log.w(f"[{host_port}] 이미 다른 컨테이너에서 사용 중인 포트입니다.")
                raise RuntimeError(f"이미 사용 중인 포트: {host_port}")

        # 공개키 로드
        try:
            with open(public_key_path, "r", encoding="utf-8") as f:
                public_key = f.read().strip()
            Log.d(f"공개키 로드 성공: {public_key_path}")
        except Exception as e:
            Log.e(f"공개키 파일 읽기 실패: {e}")
            raise RuntimeError(f"공개키 파일 읽기 실패: {e}")


        # 기본 run_command
        run_command = [
            "docker", "run", "-d",
            "-e", f'PUBLIC_KEY="{public_key}"',
        ]

        # 포트 추가
        for host_port, container_port in ports:
            run_command += ["-p", f"{host_port}:{container_port}"]

        # 조건부 환경변수 추가
        if set_jupyter_lab:
            run_command += ["-p", f'8888:8888']
            run_command += ["-e", f'JUPYTER_PASSWORD="jupyterpassword"']

        # 나머지 고정 옵션 추가
        run_command += [
            "--name", name,
            image
        ]

        docker_command = ' '.join(run_command)
        Log.d(f"Docker 실행 명령: {docker_command}")

        result = self.executor.execute(docker_command)
        if result["returncode"] != 0:
            Log.e(f"컨테이너 생성 실패: {result['stderr']}")
            raise RuntimeError(f"컨테이너 생성 실패: {result['stderr']}")
        Log.i(f"컨테이너 생성 성공: {name}")

        identity_file = private_key_path if private_key_path else public_key_path.removesuffix(".pub")

        # container_profile 구성
        container_profile = self._build_container_profile(
            name=name,
            port=ssh_port,
            identity_file=identity_file
        )

        profile = ContainerProfile(
            name=name,
            host_profile=self.host_profile,
            container_profile=container_profile,
            ssh_port=ssh_port,
            image_address=image
        )  

        # register_ssh가 참인 경우 ssh config에 생성된 container_profile 추가 
        if register_ssh:
            SSHConfigManager.add_profile(container_profile)

        try:
            self._wait_for_ssh_ready(ssh_profile=container_profile, timeout=180, interval=10)
        except TimeoutError as e:
            # SSH 접속 불가 시 컨테이너 제거
            Log.e(f"[{name}] SSH 연결 준비 타임아웃: {e}")
            try:
                self.delete_container(container=profile, force=True)
            except RuntimeError as cleanup_error:
                Log.w(f"[{name}] 타임아웃 후 정리 실패: {cleanup_error}")
            raise RuntimeError(f"[{name}] SSH 연결 실패로 컨테이너 생성 중단")
        self._setup_container_env(container=profile)

        return profile


    def commit_container(self, container: ContainerProfile, image_name: str, tag: str = "latest") -> SSHResult:
        name = container["name"]

        if not self.is_container_running(container):
            Log.w(f"[{name}] 컨테이너가 실행 중이 아니므로 커밋할 수 없습니다.")
            raise RuntimeError(f"컨테이너가 실행 중이 아닙니다: {name}")

        full_image = f"{image_name}:{tag}"
        command = f"docker commit {shlex.quote(name)} {shlex.quote(full_image)}"

        Log.d(f"[{name}] 이미지 커밋 명령어: {command}")
        result = self.executor.execute(command)

        if result["returncode"] != 0:
            Log.e(f"[{name}] 컨테이너 커밋 실패: {result['stderr']}")
            raise RuntimeError(f"컨테이너 커밋 실패: {result['stderr']}")

        Log.i(f"[{name}] 커밋 성공 → {full_image}")
        return result
    

    def list_containers(self, status: Literal["running", "all", "exited"] = "running") -> list[ContainerProfile]:
        """지정한 상태의 컨테이너들을 ContainerProfile로 반환"""
        Log.i(f"컨테이너 목록 조회: 상태={status}")

        status_filter = {
            "running": "--filter status=running",
            "exited": "--filter status=exited",
            "all": ""
        }[status]

        command = f"docker ps -a {status_filter} --format '{{{{.Names}}}}|||{{{{.Image}}}}|||{{{{.Ports}}}}'"
        result = self.executor.execute(command)

        if result["returncode"] != 0:
            Log.e(f"컨테이너 목록 조회 실패: {result['stderr']}")
            raise RuntimeError(f"컨테이너 목록 조회 실패: {result['stderr']}")

        profiles: list[ContainerProfile] = []
        for line in result["stdout"].splitlines():
            name, image, ports = line.strip().split("|||")

            # SSH 포트 추출
            try:
                ssh_port = self._extract_ssh_port(ports)
            except ValueError:
                ssh_port = ""
                
            container_profile = self._build_container_profile(
                name=name,
                port=ssh_port,
                identity_file=self.host_profile.get("identity_file", None)
            )

            profile: ContainerProfile = {
                "name": name,
                "host_profile": self.host_profile,
                "container_profile": container_profile,
                "ssh_port": ssh_port,
                "image_address": image
            }
            profiles.append(profile)

        Log.d(f"{len(profiles)}개의 컨테이너 검색됨")
        return profiles


    def list_images(self, show_dangling: bool = False) -> list[dict[str, str]]:
        format_str = "'{{.Repository}}||{{.Tag}}||{{.ID}}||{{.CreatedSince}}||{{.Size}}'"
        cmd = ["docker", "images", "--format", format_str]

        if not show_dangling:
            cmd += ["--filter", "dangling=false"]

        result = self.executor.execute(" ".join(cmd))
        lines = result["stdout"].strip().splitlines()

        images: list[dict[str, str]] = []
        for line in lines:
            parts = line.split("||")
            if len(parts) != 5:
                continue
            repository, tag, image_id, created, size = parts
            images.append({
                "repository": repository,
                "tag": tag,
                "image_id": image_id,
                "created": created,
                "size": size
            })

        return images


    def delete_container(self, container: ContainerProfile, force: bool = False, remove_ssh: bool = False) -> SSHResult:
        """지정한 컨테이너 삭제. 실행 중이면 force=True일 때만 삭제 가능"""
        name = container["name"]
        Log.i(f"[{name}] 컨테이너 삭제 시도 (force={force})")

        if self.is_container_running(container):
            if not force:
                Log.w(f"[{name}] 실행 중인 컨테이너는 force=True일 때만 삭제할 수 있습니다.")
                raise RuntimeError(f"[{name}] 실행 중인 컨테이너는 삭제할 수 없습니다. force=True를 사용하세요.")

            Log.i(f"[{name}] 컨테이너가 실행 중이므로 정지 후 삭제합니다.")
            self.stop_container(container)

        command = f"docker rm {shlex.quote(name)}"
        Log.d(f"[{name}] 컨테이너 삭제 명령어: {command}")

        result = self.executor.execute(command)

        if result["returncode"] != 0:
            Log.e(f"[{name}] 컨테이너 삭제 실패: {result['stderr']}")
            raise RuntimeError(f"컨테이너 삭제 실패: {result['stderr']}")

        # remove_ssh가 참인 경우 ssh config에서 container_profile 제거 
        if remove_ssh:
            SSHConfigManager.remove_profile(container["container_profile"])

        Log.i(f"[{name}] 컨테이너 삭제 완료")
        return result


    def is_container_running(self, container: ContainerProfile) -> bool:
        """지정한 컨테이너가 실행 중인지 확인"""
        name = container["name"]
        command = f'docker ps --filter name={shlex.quote(name)} --filter status=running --format "{{{{.Names}}}}"'

        result = self.executor.execute(command)
        if result["returncode"] != 0:
            Log.w(f"컨테이너 실행 상태 확인 실패: {result['stderr']}")
            raise RuntimeError(f"컨테이너 실행 상태 확인 실패: {result['stderr']}")

        running_names = result["stdout"].splitlines()
        is_running = name in running_names

        Log.d(f"[{name}] 실행 중 여부: {is_running}")
        return is_running
    

    def start_container(self, container: ContainerProfile) -> SSHResult:
        """지정한 컨테이너를 실행 상태로 시작"""
        name = container["name"]
        Log.i(f"[{name}] 컨테이너 시작 시도")

        if self.is_container_running(container):
            Log.i(f"[{name}] 이미 실행 중입니다. 시작 생략")
            return {
                "returncode": 0,
                "stdout": f"{name} already running",
                "stderr": ""
            }

        command = f"docker start {shlex.quote(name)}"
        Log.d(f"[{name}] 컨테이너 시작 명령어: {command}")

        result = self.executor.execute(command)

        if result["returncode"] != 0:
            Log.e(f"[{name}] 컨테이너 시작 실패: {result['stderr']}")
            raise RuntimeError(f"컨테이너 시작 실패: {result['stderr']}")

        Log.i(f"[{name}] 컨테이너 시작 완료")
        return result


    def stop_container(self, container: ContainerProfile) -> SSHResult:
        """지정한 컨테이너를 정지"""
        name = container["name"]
        Log.i(f"[{name}] 컨테이너 정지 시도")

        if not self.is_container_running(container):
            Log.i(f"[{name}] 컨테이너가 이미 정지 상태입니다. 중단 생략")
            return {
                "returncode": 0,
                "stdout": f"{name} already stopped",
                "stderr": ""
            }

        command = f"docker stop {shlex.quote(name)}"
        Log.d(f"[{name}] 컨테이너 정지 명령어: {command}")

        result = self.executor.execute(command)

        if result["returncode"] != 0:
            Log.e(f"[{name}] 컨테이너 정지 실패: {result['stderr']}")
            raise RuntimeError(f"컨테이너 정지 실패: {result['stderr']}")

        Log.i(f"[{name}] 컨테이너 정지 완료")
        return result


    def container_exists(self, name: str) -> bool:
        """지정한 이름의 컨테이너가 존재하는지 확인"""
        command = "docker ps -a --format '{{.Names}}'"

        result = self.executor.execute(command)
        if result["returncode"] != 0:
            Log.w(f"컨테이너 목록 조회 실패: {result['stderr']}")
            raise RuntimeError(f"컨테이너 목록 조회 실패: {result['stderr']}")

        existing_names = result["stdout"].splitlines()
        exists = name in existing_names

        Log.d(f"컨테이너 존재 여부 확인: name={name}, exists={exists}")
        return exists


    def _extract_ssh_port(self, ports: str) -> str:
        # 예: "0.0.0.0:2222->22/tcp, [::]:2222->22/tcp"
        for segment in ports.split(","):
            segment = segment.strip()
            if "->22" in segment:
                match = re.search(r":(\d+)->22", segment)
                if match:
                    return match.group(1)
        raise ValueError(f"SSH 포트 추출 실패: {ports}")


    def _build_container_profile(self, name: str, port: str, identity_file: str | None = None) -> SSHProfile:
        return {
            "host": name,
            "hostname": self.host_profile["hostname"],
            "port": port,
            "user": "root",
            "identity_file": identity_file,
        }


    def _is_port_in_use(self, port: str) -> bool:
        command = "docker ps -a --format '{{.Ports}}'"
        result = self.executor.execute(command)
        if result["returncode"] != 0:
            Log.w(f"포트 확인 명령 실패: {result['stderr']}")
            raise RuntimeError(f"포트 확인 명령 실패: {result['stderr']}")

        for line in result["stdout"].splitlines():
            if f":{port}->22" in line or f":{port}->" in line:
                Log.d(f"[포트 충돌 확인] 사용 중인 포트 발견: {port}")
                return True
        return False


    def _wait_for_ssh_ready(self, ssh_profile: SSHProfile, timeout: int = 60, interval: int = 5) -> None:
        start = time.time()
        step_id = Log.start("SSH 연결 준비")
        ssh_executor = SSHExecutor(profile=ssh_profile)
        while time.time() - start < timeout:
            try: 
                result = ssh_executor.execute("echo ready", log=False, StrictHostKeyChecking=False)
                if result["returncode"] == 0:
                    Log.end(step_id=step_id)
                    return
            except Exception:
                pass
            Log.v(f"SSH 미연결 상태, {interval}초 이후 재시도")
            time.sleep(interval)
        Log.end(step_id=step_id)
        Log.e(f"[{ssh_profile["host"]}] SSH 연결 실패 (timeout {timeout}s)")
        raise TimeoutError(f"[{ssh_profile["host"]}] SSH 연결 실패 (timeout {timeout}s)")


    def _setup_container_env(self, container: ContainerProfile) -> None:
        step_id = Log.start(f"[{container["name"]}] 컨테이너 환경 설정 시작")

        base_apt_packages = ["rsync", "curl", "jq", "socat"]
        base_pip_packages = ["runpod", "matplotlib"]
        install_cmd = [f"apt update -qq 2>/dev/null",
                       f"DEBIAN_FRONTEND=noninteractive apt-get install -y -qq {' '.join(base_apt_packages)}",
                       f"pip install -qq {' '.join(base_pip_packages)}"]
        Log.v(f"[{container["name"]}] 패키지 설치 명령: {install_cmd}")

        result = SSHExecutor(profile=container["container_profile"]).execute(install_cmd)

        if result["returncode"] != 0:
            Log.e(f"[{container["name"]}] 패키지 설치 실패: {result["stderr"]}")
            raise RuntimeError(f"컨테이너 환경 설정 실패: {result["stderr"]}")
        
        result = SSHExecutor(profile=container["container_profile"]).upload_file(
            local_path=r"container_setup\DOLAB", remote_path=r"/root/")

        result = SSHExecutor(profile=container["container_profile"]).upload_file(
            local_path=r"container_setup\workspace", remote_path=r"/")
        
        if not result:
            Log.e(f"[{container["name"]}] 기본 폴더 업로드 실패")
            raise RuntimeError(f"컨테이너 환경 설정 실패")
        
        chmod_cmd = "chmod +x /root/DOLAB/* && chmod +x /workspace/*"
        result = SSHExecutor(profile=container["container_profile"]).execute(chmod_cmd)

        Log.end(step_id=step_id)