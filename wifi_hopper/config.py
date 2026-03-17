from dataclasses import dataclass, field


@dataclass
class HopperConfig:
    poll_interval: int = 30
    interface: str = "WiFi"
    log_file: str = "wifi_hopper.log"
    blacklist: list = field(default_factory=list)
    min_signal: int = 50
    dwell_time: int = 120
    dry_run: bool = False
    disconnect_on_exit: bool = False
