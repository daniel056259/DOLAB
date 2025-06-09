from typing import TypedDict

class SSHResult(TypedDict):
    returncode: int
    stdout: str
    stderr: str