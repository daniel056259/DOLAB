from libs import cli
from libs.ssh_config_manager import SSHConfigManager
from libs.logger import Log, LogLevel
from libs.host_machine import HostMachine
from libs.runpod_manager import RunPodManager

Log.set_console_output(False)
Log.set_log_file("./logs")

def main():
    runpod_manager = RunPodManager()
    host_machine: HostMachine | None = None

    def ensure_host_machine() -> HostMachine:
        nonlocal host_machine
        if not host_machine:
            print("SSH 호스트가 선택되지 않았습니다. 선택이 필요합니다.")
            host_profile = cli.select_host()
            host_machine = HostMachine(ssh_profile=host_profile)
        return host_machine

    menu_options = {
        "1": "컨테이너 생성",
        "2": "컨테이너 재개",
        "3": "컨테이너 정지",
        "4": "컨테이너 커밋",
        "5": "컨테이너 제거",
        "6": "도커 이미지 DockerHub 푸시",
        "7": "Pod 생성 (RunPod)",
        "8": "Pod 제거 (RunPod)",
        "0": "종료"
    }

    while True:
        print("\n=== 작업 선택 ===")
        for key, desc in menu_options.items():
            print(f"{key}. {desc}")

        choice = input("번호를 선택하세요: ").strip()

        try:
            if choice == "1":
                cli.create_container(host_machine=ensure_host_machine())

            elif choice == "2":
                container = cli.select_container(host_machine=ensure_host_machine())
                ensure_host_machine().start_container(container=container)

            elif choice == "3":
                container = cli.select_container(host_machine=ensure_host_machine())
                ensure_host_machine().stop_container(container=container)

            elif choice == "4":
                cli.commit_container(host_machine=ensure_host_machine())

            elif choice == "5":
                profile = cli.select_container(host_machine=ensure_host_machine())
                ensure_host_machine().delete_container(profile, force=True, remove_ssh=True)

            elif choice == "6":
                cli.tag_and_push_to_dockerhub(host_machine=ensure_host_machine())

            elif choice == "7":
                cli.create_pod(runpod_manager=runpod_manager, host_machine=ensure_host_machine())

            elif choice == "8":
                pod_profile = cli.select_pods(runpod_manager)
                if pod_profile:
                    runpod_manager.terminate_pod(pod=pod_profile)
                    SSHConfigManager.remove_profile(
                        profile=pod_profile["ssh_profile"])

            elif choice == "0":
                print("프로그램을 종료합니다.")
                break

            else:
                print("유효하지 않은 번호입니다.")

        except Exception as e:
            Log.e(e)


if __name__ == "__main__":
    main()
