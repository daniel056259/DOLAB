from typing import TypedDict, Literal
from .ssh_profile import SSHProfile

class GpuType(TypedDict):
    maxGpuCount: int
    id: str
    displayName: str
    memoryInGb: int
    secureCloud: bool
    communityCloud: bool
    securePrice: float
    communityPrice: float

class RunPodPort(TypedDict):
    ip: str
    is_ip_public: bool
    private_port: int
    public_port: int
    type: Literal["tcp", "http"]

class RunPodProfile(TypedDict):
    id: str
    name: str
    image_name: str
    desired_status: Literal["RUNNING", "STOPPED", "TERMINATED", "PAUSED"]
    cost_per_hr: float
    gpu_count: int
    memory_in_gb: int
    vcpu_count: int
    container_disk_in_gb: int
    machine_id: str
    gpu_display_name: str
    ports: list[RunPodPort]

    ssh_public_ip: str
    ssh_port: int
    jupyter_enabled: bool

    ssh_profile: SSHProfile