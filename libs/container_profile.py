from typing import TypedDict
from .ssh_profile import SSHProfile

class ContainerProfile(TypedDict):
    name: str
    host_profile: SSHProfile
    container_profile: SSHProfile
    ssh_port: str
    image_address: str