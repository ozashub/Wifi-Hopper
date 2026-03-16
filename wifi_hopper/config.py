from dataclasses import dataclass, field


@dataclass
class HopperConfig:
    poll_interval: int = 30          # seconds between scans
    interface: str = "WiFi"          # netsh interface name
    log_file: str = "wifi_hopper.log"
    blacklist: list = field(default_factory=list)   # SSIDs to never connect to
    min_signal: int = 50             # minimum signal % to attempt connection
    dwell_time: int = 120            # seconds to stay on a network before re-evaluating
    dry_run: bool = False            # scan and log only, never actually connect
    disconnect_on_exit: bool = False  # disconnect when the hopper is stopped
