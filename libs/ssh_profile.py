from typing import TypedDict, Optional

class SSHProfile(TypedDict):
    host: str
    hostname: str
    port: str
    user: str
    identity_file: Optional[str]