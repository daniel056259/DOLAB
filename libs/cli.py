from .ssh_config_manager import SSHConfigManager
from .ssh_profile import SSHProfile
from .host_machine import HostMachine
from .container_profile import ContainerProfile
from .dockerhub_manager import DockerHubManager
from .runpod_profile import GpuType
from .runpod_manager import RunPodManager, RunPodProfile
from .ssh_key_provisioner import SSHKeyProvisioner
from .pod_info import PodInfoBuilder, PodInfoUploader
from typing import Literal
from tabulate import tabulate
from pathlib import Path
import json
import os

CONFIG_PATH = Path("./.config/.cli_config.json")

def _ensure_config_file_exists():
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with CONFIG_PATH.open("w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)

def get_cli_config(key: str, prompt: str, default_value: str = "") -> str:
    _ensure_config_file_exists()

    # 읽기
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        config = json.load(f)

    # 존재 여부 확인
    value = config.get(key)
    if value:
        return value

    # 값이 없을 경우 입력받아 저장
    value = input(f"{prompt}: ").strip() or default_value
    config[key] = value

    with CONFIG_PATH.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    return value

def select_host() -> SSHProfile:
    hosts = SSHConfigManager.read_all_hosts()

    if not hosts:
        raise RuntimeError("선택 가능한 SSH 호스트가 없습니다.")

    print("SSH 호스트를 선택하세요:")
    for i, host in enumerate(hosts, start=1):
        print(f"{i}. {host}")

    while True:
        try:
            index = int(input("번호 입력: "))
            if 1 <= index <= len(hosts):
                selected_host = hosts[index - 1]
                break
            else:
                print("유효한 번호를 입력하세요.")
        except ValueError:
            print("숫자를 입력해주세요.")

    return SSHConfigManager.read_profile(selected_host)

def create_container(host_machine: HostMachine) -> ContainerProfile:
    default_image_path = get_cli_config(
        key="default_image_path", prompt="기본 RunPod 이미지 정보가 있는 images.json 파일의 경로를 입력하세요", default_value="./images.json")
    default_images = []
    if Path(default_image_path).exists():
        with open(default_image_path, "r", encoding="utf-8") as f:
            default_images = json.load(f)
    else:
        print(f"[경고] 기본 이미지 목록 파일이 없습니다: {default_image_path}")

    while True:
        name = input("컨테이너 이름을 입력하세요: ").strip()
        if not name:
            print("이름은 비워둘 수 없습니다.")
            continue
        if host_machine.container_exists(name):
            print(f"이미 존재하는 컨테이너 이름입니다: {name}")
            continue
        break

    while True:
        ports_input = input("포트 바인딩을 입력하세요 (예: 2222:22,8080:8080): ").strip()
        try:
            ports = []
            for pair in ports_input.split(","):
                host_port, container_port = pair.strip().split(":")
                if not (host_port.isdigit() and container_port.isdigit()):
                    raise ValueError
                if host_machine._is_port_in_use(host_port):
                    print(f"이미 사용 중인 포트입니다: {host_port}")
                    raise ValueError
                ports.append((host_port, container_port))
            # 반드시 22번 컨테이너 포트가 포함되어야 함
            if not any(container_port == "22" for _, container_port in ports):
                print("반드시 컨테이너의 22번 포트(SSH)를 바인딩해야 합니다. 예: 2222:22")
                continue
            break
        except ValueError:
            print("형식이 올바르지 않거나 포트가 중복되었습니다. 예: 2222:22,8080:8080")
            continue

    image_address = ""
    if default_images:
        print("사용할 기본 이미지를 선택하세요:")
        for i, img in enumerate(default_images, 1):
            print(f"{i}. {img['name']}  ({img['image']})")
        print(f"{len(default_images)+1}. 직접 이미지 주소 입력")

        while True:
            try:
                idx = int(input("번호 선택: "))
                if 1 <= idx <= len(default_images):
                    image_address = default_images[idx - 1]["image"]
                    break
                elif idx == len(default_images) + 1:
                    image_address = input("이미지 주소 입력: ").strip()
                    if image_address:
                        break
                print("유효한 번호를 입력해주세요.")
            except ValueError:
                print("숫자를 입력해주세요.")
    else:
        image_address = input("이미지 주소 입력: ").strip()

    default_public = str(Path.home() / ".ssh/id_ed25519.pub")
    public_key_path = get_cli_config(key="public_key_path", prompt=f"공개키 경로 입력 (기본값: {default_public})", default_value=default_public)
    public_key_path = os.path.expanduser(public_key_path)

    default_private =  public_key_path.removesuffix(".pub")
    private_key_path = get_cli_config(key="private_key_path", prompt=f"개인키 경로 입력 (기본값: {default_private})", default_value=default_private)
    private_key_path = os.path.expanduser(private_key_path)

    set_jupyter = (input("Jupyter Lab을 활성화하시겠습니까? (y/N): ").strip().lower() or "n") == "y"

    register_ssh = (input("SSH config에 자동 등록하시겠습니까? (Y/n): ").strip().lower() or "y") == "y"

    return host_machine.create_container(
        name=name, 
        image=image_address, 
        ports=ports, 
        public_key_path=public_key_path, 
        private_key_path=private_key_path, 
        set_jupyter_lab=set_jupyter, 
        register_ssh=register_ssh
    )

def select_container(host_machine: HostMachine) -> ContainerProfile:
    container_status: list[Literal["running", "all", "exited"]] = ["running", "all", "exited"]

    print("검색할 컨테이너 상태를 선택하세요:")
    for i, status in enumerate(container_status, start=1):
        print(f"{i}. {status}")

    while True:
        try:
            index = int(input("번호 입력: "))
            if 1 <= index <= len(container_status):
                selected_status = container_status[index - 1]
                break
            else:
                print("유효한 번호를 입력하세요.")
        except ValueError:
            print("숫자를 입력해주세요.")

    container_profile_list: list[ContainerProfile] = host_machine.list_containers(status=selected_status)

    if not container_profile_list:
        raise RuntimeError("선택 가능한 컨테이너가 없습니다.")
    
    print("컨테이너를 선택하세요:")
    for i, container_profile in enumerate(container_profile_list, start=1):
        print(f"{i}. {container_profile["name"]}")

    while True:
        try:
            index = int(input("번호 입력: "))
            if 1 <= index <= len(container_profile_list):
                selected_container = container_profile_list[index - 1]
                break
            else:
                print("유효한 번호를 입력하세요.")
        except ValueError:
            print("숫자를 입력해주세요.")

    return selected_container

def _print_gpu_options(gpu_info_list: list[GpuType], cloud_type: Literal["ALL", "SECURE", "COMMUNITY"]) -> None:
    table = []

    for idx, gpu in enumerate(gpu_info_list, start=1):
        name = gpu["displayName"]
        count = gpu["maxGpuCount"]
        vram = f"{gpu['memoryInGb']} GB"

        secure_price = f"${gpu['securePrice']:.2f}" if gpu.get("secureCloud") else ""
        community_price = f"${gpu['communityPrice']:.2f}" if gpu.get("communityCloud") else ""

        # 열 구성 조건
        if cloud_type == "SECURE":
            row = [idx, name, count, vram, secure_price]
        elif cloud_type == "COMMUNITY":
            row = [idx, name, count, vram, community_price]
        else:  # "ALL"
            row = [idx, name, count, vram, secure_price, community_price]

        table.append(row)

    # 헤더 구성 조건
    if cloud_type == "SECURE":
        headers = ["번호", "이름", "GPU 수", "VRAM", "Secure Cloud 요금"]
    elif cloud_type == "COMMUNITY":
        headers = ["번호", "이름", "GPU 수", "VRAM", "Community Cloud 요금"]
    else:
        headers = ["번호", "이름", "GPU 수", "VRAM", "Secure Cloud 요금", "Community Cloud 요금"]

    print(tabulate(table, headers=headers, tablefmt="pretty"))

def _select_cloud_type() -> Literal["ALL", "SECURE", "COMMUNITY"]:
    cloud_options: list[Literal["ALL", "SECURE", "COMMUNITY"]] = ["ALL", "SECURE", "COMMUNITY"]
    print("검색할 cloud 옵션을 선택하세요:")
    for i, cloud_option in enumerate(cloud_options, start=1):
        print(f"{i}. {cloud_option}")

    while True:
        try:
            index = int(input("번호 입력: "))
            if 1 <= index <= len(cloud_options):
                selected_cloud = cloud_options[index - 1]
                break
            else:
                print("유효한 번호를 입력하세요.")
        except ValueError:
            print("숫자를 입력해주세요.")
    
    return selected_cloud

def select_gpus(cloud_type: Literal["ALL", "SECURE", "COMMUNITY"]) -> list[str]:
    all_gpus: list[GpuType] = RunPodManager.get_gpus_detailed()
    selected_gpus: list[str] = []

    available_gpus: list[GpuType] = []
    if cloud_type == "SECURE":
        available_gpus = [gpu for gpu in all_gpus if gpu.get("secureCloud")]
    elif cloud_type == "COMMUNITY":
        available_gpus = [gpu for gpu in all_gpus if gpu.get("communityCloud")]
    else:
        available_gpus = [gpu for gpu in all_gpus if gpu.get("secureCloud") or gpu.get("communityCloud")]

    print("\n사용할 GPU를 우선순위에 따라 선택하세요 (예: 1,3,4):")
    _print_gpu_options(available_gpus, cloud_type)

    while True:
        user_input = input("번호(쉼표로 구분): ").strip()
        try:
            indexes = [int(i.strip()) for i in user_input.split(",") if i.strip()]
            if any(i < 1 or i > len(available_gpus) for i in indexes):
                print("범위를 벗어난 번호가 포함되어 있습니다. 다시 입력하세요.")
                continue
            selected_gpus = [available_gpus[i - 1]["id"] for i in indexes]
            break
        except ValueError:
            print("숫자만 입력하세요. 예: 1,2,3")

    return selected_gpus

def select_pods(runpod_manager: RunPodManager) -> RunPodProfile | None:
    pods = runpod_manager.get_pods()
    if not pods:
        print("사용 가능한 Pod가 없습니다.")
        return

    # 표 데이터 구성
    table = []
    for idx, pod in enumerate(pods, start=1):
        table.append([
            idx,
            pod.get("name", ""),
            pod.get("machine", {}).get("gpuDisplayName", ""),
            pod.get("gpuCount", 0)
        ])

    headers = ["번호", "Pod 이름", "GPU 이름", "GPU 개수"]
    print(tabulate(table, headers=headers, tablefmt="pretty"))

    # 사용자 입력
    while True:
        try:
            index = int(input("선택할 번호 입력: "))
            if 1 <= index <= len(pods):
                return runpod_manager.convert_to_runpod_profile(pods[index - 1])
            else:
                print("유효한 번호를 입력하세요.")
        except ValueError:
            print("숫자를 입력해주세요.")

def commit_container(host_machine: HostMachine) -> str:
    container = select_container(host_machine=host_machine)

    while True:
        commit_image_name = input("생성할 이미지의 이름을 입력하세요: ").strip()
        if commit_image_name:
            break
        print("이미지 이름은 필수입니다.")

    commit_tag = input("이미지 태그를 입력하세요 (기본값: 'latest'): ").strip() or "latest"

    print(f"[INFO] 컨테이너 '{container['name']}'을(를) 이미지 '{commit_image_name}:{commit_tag}'로 커밋합니다...")
    host_machine.commit_container(container=container, image_name=commit_image_name, tag=commit_tag)
    print("[완료] 이미지 커밋이 완료되었습니다.")
    return f"{commit_image_name}:{commit_tag}"

def select_local_image(host_machine: HostMachine) -> str | None:
    images = host_machine.list_images()
    if not images:
        print("선택 가능한 이미지가 없습니다.")
        return
    
    images = images[:30]
    
    # 표 데이터 구성
    table = []
    for idx, image in enumerate(images, start=1):
        table.append([
            idx,
            f"{image["repository"]}:{image["tag"]}",
            image["created"],
            image["size"]
        ])

    headers = ["번호", "이미지", "생성 날짜", "크기"]
    print(tabulate(table, headers=headers, tablefmt="pretty"))

    # 사용자 입력
    while True:
        try:
            index = int(input("선택할 번호 입력: "))
            if 1 <= index <= len(images):
                return f"{images[index - 1]["repository"]}:{images[index - 1]["tag"]}"
            else:
                print("유효한 번호를 입력하세요.")
        except ValueError:
            print("숫자를 입력해주세요.")

def tag_and_push_to_dockerhub(host_machine: HostMachine) -> str | None:
    dockerhub_username = get_cli_config(key="dockerhub_username", prompt="DockerHub 사용자명을 입력하세요")
    dockerhub_manager = DockerHubManager(host_machine=host_machine, dockerhub_username=dockerhub_username)

    if not dockerhub_manager.is_logged_in():
        print(f"[오류] 호스트 '{host_machine.host_profile['host']}'에서 '{dockerhub_username}' 계정으로 DockerHub에 로그인되어 있지 않습니다.")
        print("DockerHub에 로그인하려면 해당 호스트에서 'docker login'을 먼저 실행해 주세요.")
        return None

    local_image = select_local_image(host_machine=host_machine)
    if not local_image: 
        print("이미지가 지정되지 않아 동작을 취소합니다.")
        return

    while True:
        repo = input("DockerHub 저장소 이름(repository)을 입력하세요: ").strip()
        if repo:
            break
        print("저장소 이름은 필수입니다.")

    repo_tag = input("저장소 태그를 입력하세요 (기본값: 'latest'): ").strip() or "latest"

    print(f"[INFO] 태그 지정 중: {local_image} → {dockerhub_username}/{repo}:{repo_tag}")
    dockerhub_manager.tag_image(local_image=local_image, repository=repo, tag=repo_tag)
    print("[완료] 태그 지정 완료.")

    print("[INFO] DockerHub로 이미지 푸시 중... (수 분 소요될 수 있습니다.)")
    dockerhub_manager.push_image(repository=repo, tag=repo_tag)
    print(f"[완료] DockerHub 푸시 완료: {dockerhub_username}/{repo}:{repo_tag}")

    return f"{dockerhub_username}/{repo}:{repo_tag}"

def create_pod(runpod_manager: RunPodManager, host_machine: HostMachine) -> RunPodProfile:
    name = input("Pod 이름을 입력하세요: ").strip()
    if not name:
        raise ValueError("Pod 이름은 필수입니다.")

    dockerhub_username = get_cli_config(key="dockerhub_username", prompt="DockerHub 사용자명을 입력하세요")
    dockerhub_manager = DockerHubManager(host_machine, dockerhub_username)

    repos = dockerhub_manager.get_repos()
    if not repos:
        raise RuntimeError("DockerHub에 사용 가능한 저장소가 없습니다.")

    print("사용할 DockerHub 저장소를 선택하세요:")
    for i, repo in enumerate(repos, 1):
        print(f"{i}. {repo}")
    while True:
        try:
            repo_index = int(input("저장소 번호 입력: "))
            if 1 <= repo_index <= len(repos):
                selected_repo = repos[repo_index - 1]
                break
        except ValueError:
            pass
        print("유효한 번호를 입력해주세요.")

    tags = dockerhub_manager.get_repo_tags(repo=selected_repo)
    if not tags:
        raise RuntimeError("선택한 저장소에 사용 가능한 태그가 없습니다.")

    print("사용할 태그를 선택하세요:")
    for i, tag in enumerate(tags, 1):
        print(f"{i}. {tag}")
    while True:
        try:
            tag_index = int(input("태그 번호 입력: "))
            if 1 <= tag_index <= len(tags):
                selected_tag = tags[tag_index - 1]
                break
        except ValueError:
            pass
        print("유효한 번호를 입력해주세요.")

    image_name = f"{dockerhub_username}/{selected_repo}:{selected_tag}"

    cloud_type = _select_cloud_type()
    gpu_ids = select_gpus(cloud_type=cloud_type)

    while True:
        gpu_count_input = input("사용할 GPU 개수 입력 (기본값 1): ").strip()
        if gpu_count_input == "":
            gpu_count = 1
            break
        elif gpu_count_input.isdigit():
            gpu_count = int(gpu_count_input)
            break
        else:
            print("숫자를 입력해주세요.")

    disk_input = input("컨테이너 디스크 크기 (GB, 선택 사항): ").strip()
    container_disk_in_gb = int(disk_input) if disk_input.isdigit() else None

    jupyter = (input("Jupyter Lab을 활성화하시겠습니까? (y/N): ").strip().lower() or "n") == "y"

    register_ssh = (input("SSH config에 자동 등록하시겠습니까? (Y/n): ").strip().lower() or "y") == "y"

    pod = runpod_manager.create_pod(
        name=name,
        image_name=image_name,
        gpu_type_id=gpu_ids,
        cloud_type=cloud_type,
        gpu_count=gpu_count,
        container_disk_in_gb=container_disk_in_gb,
        start_jupyter=jupyter
    )

    print("동기화할 컨테이너를 선택하세요")
    sync_target_container = select_container(host_machine=host_machine)

    key_provisioner = SSHKeyProvisioner()
    private_key_path, public_key_path = key_provisioner.generate_keypair()
    key_provisioner.upload_public_key_to_pod(ssh_profile=pod["ssh_profile"], public_key_path=public_key_path)
    key_provisioner.upload_private_key_to_container(ssh_profile=sync_target_container["container_profile"], private_key_path=private_key_path)

    pod_info = PodInfoBuilder.build(runpod_profile=pod, runpod_api_key=runpod_manager.get_api_key(), identity_file_path=f"~/.ssh/{key_provisioner.key_name}")
    PodInfoUploader.upload(info=pod_info, ssh_profile=sync_target_container["container_profile"])

    if register_ssh:
        SSHConfigManager.add_profile(pod["ssh_profile"])

    return pod