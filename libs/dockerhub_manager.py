from .host_machine import HostMachine
from .logger import Log
import shlex
import requests

class DockerHubManager:
    def __init__(self, host_machine: HostMachine, dockerhub_username: str):
        self.executor = host_machine.executor
        self.username = dockerhub_username


    def is_logged_in(self) -> bool:
        """도커가 지정된 username으로 로그인된 상태인지 확인"""
        command = "docker info | grep Username:"
        result = self.executor.execute(command)

        if result["returncode"] != 0:
            Log.e(f"도커 로그인 상태 확인 실패: {result['stderr']}")
            raise RuntimeError(f"도커 로그인 상태 확인 실패: {result['stderr']}")

        for line in result["stdout"].splitlines():
            if line.strip().startswith("Username:"):
                current_user = line.split(":", 1)[1].strip()
                match = (current_user == self.username)
                Log.i(f"DockerHub 로그인 사용자: {current_user} → {'일치' if match else '불일치'}")
                return match

        Log.i("DockerHub 로그인 정보 없음 (Username 항목 미포함)")
        return False

    def tag_image(self, local_image: str, repository: str, tag: str = "latest") -> None:
        """로컬 이미지를 DockerHub용으로 태깅"""
        full_tag = f"{self.username}/{repository}:{tag}"
        command = f"docker tag {shlex.quote(local_image)} {shlex.quote(full_tag)}"
        Log.d(f"도커 이미지 태그 명령어: {command}")

        result = self.executor.execute(command)
        if result["returncode"] != 0:
            Log.e(f"이미지 태그 실패: {result['stderr']}")
            raise RuntimeError(f"이미지 태그 실패: {result['stderr']}")

    def push_image(self, repository: str, tag: str = "latest") -> None:
        """태그된 이미지를 DockerHub로 푸시"""
        full_image = f"{self.username}/{repository}:{tag}"
        command = f"docker push --quiet {shlex.quote(full_image)}"
        Log.d(f"도커 푸시 명령어: {command}")

        result = self.executor.execute(command)
        if result["returncode"] != 0:
            Log.e(f"이미지 푸시 실패: {result['stderr']}")
            raise RuntimeError(f"이미지 푸시 실패: {result['stderr']}")

    def get_repos(self, page: int = 1, page_size: int = 100) -> list[str]:
        url = f"https://hub.docker.com/v2/repositories/{self.username}/"
        params = {"page": page, "page_size": page_size}
        repos = []

        while url:
            resp = requests.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            repos.extend([repo["name"] for repo in data["results"]])
            url = data["next"]  # 다음 페이지 있으면 계속

        return repos

    def get_repo_tags(self, repo: str, page_size: int = 100) -> list[str]:
        tags_url = f"https://hub.docker.com/v2/repositories/{self.username}/{repo}/tags"
        tags: list[str] = []

        while tags_url:
            response = requests.get(tags_url, params={"page_size": page_size})
            if response.status_code != 200:
                Log.w(f"태그 정보를 가져오는 데 실패했습니다: {response.status_code}")
                raise RuntimeError(f"태그 정보를 가져오는 데 실패했습니다: {response.status_code}")
            data = response.json()
            tags += [tag["name"] for tag in data.get("results", [])]
            tags_url = data.get("next")

        return tags
