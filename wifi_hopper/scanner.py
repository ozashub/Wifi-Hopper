import subprocess
import re
from dataclasses import dataclass


@dataclass
class OpenNetwork:
    ssid: str
    bssid: str
    signal: int  # 0-100%
    channel: int
    radio_type: str

    def __str__(self) -> str:
        return f"{self.ssid!r:35s} | signal={self.signal:3d}% | ch={self.channel:3d} | {self.radio_type}"


def scan_open_networks(interface: str) -> list:
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks", "mode=bssid"],
            capture_output=True, text=True, timeout=15,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        raise RuntimeError(f"netsh scan failed: {exc}") from exc

    output = result.stdout

    if "location" in output.lower() and len(output.strip().splitlines()) < 6:
        raise RuntimeError(
            "Location Services is blocking WiFi scans. "
            "Enable it in Settings → Privacy & Security → Location."
        )

    return _parse_networks(output)


def _parse_networks(output: str) -> list:
    networks = []
    current: dict = {}

    for raw_line in output.splitlines():
        line = raw_line.strip()

        m = re.match(r"^SSID\s+\d+\s*:\s+(.+)$", line)
        if m:
            _maybe_add(current, networks)
            current = {"ssid": m.group(1).strip(), "bssid": "", "signal": 0, "channel": 0, "radio": "unknown"}
            continue

        if not current:
            continue

        if re.match(r"^Authentication\s*:", line):
            current["auth"] = line.split(":", 1)[1].strip()
        elif re.match(r"^Encryption\s*:", line):
            current["enc"] = line.split(":", 1)[1].strip()
        elif re.match(r"^BSSID\s+\d+\s*:", line) and not current["bssid"]:
            current["bssid"] = line.split(":", 1)[1].strip()
        elif re.match(r"^Signal\s*:", line) and current["signal"] == 0:
            try:
                current["signal"] = int(line.split(":", 1)[1].strip().rstrip("%"))
            except ValueError:
                pass
        elif re.match(r"^Channel\s*:", line) and current["channel"] == 0:
            try:
                current["channel"] = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
        elif re.match(r"^Radio type\s*:", line):
            current["radio"] = line.split(":", 1)[1].strip()

    _maybe_add(current, networks)
    return networks


def _maybe_add(current: dict, networks: list) -> None:
    if not current.get("ssid"):
        return
    if current.get("auth", "").lower() != "open":
        return
    if current.get("enc", "").lower() not in ("none", ""):
        return
    networks.append(OpenNetwork(
        ssid=current["ssid"],
        bssid=current["bssid"],
        signal=current["signal"],
        channel=current["channel"],
        radio_type=current["radio"],
    ))


def get_interface_name() -> str:
    # try netsh first (needs location services on Win11)
    try:
        r = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=10,
        )
        for line in r.stdout.splitlines():
            m = re.match(r"^\s+Name\s*:\s+(.+)$", line)
            if m:
                return m.group(1).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # ipconfig works without location services
    try:
        r = subprocess.run(["ipconfig"], capture_output=True, text=True, timeout=10)
        for line in r.stdout.splitlines():
            m = re.match(r"^Wireless LAN adapter (.+?)\s*:", line)
            if m:
                return m.group(1).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    raise RuntimeError("No WLAN interface found. Is your WiFi adapter enabled?")


def ping_ms(host: str = "8.8.8.8") -> float | None:
    try:
        r = subprocess.run(
            ["ping", "-n", "4", "-w", "1000", host],
            capture_output=True, text=True, timeout=8,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
    m = re.search(r"Average\s*=\s*(\d+)ms", r.stdout)
    return float(m.group(1)) if m else None


def get_connected_ssid(interface: str) -> str | None:
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    in_iface = False
    ssid = None
    connected = False

    for line in result.stdout.splitlines():
        stripped = line.strip()
        if re.match(r"^Name\s*:", stripped):
            in_iface = stripped.split(":", 1)[1].strip().lower() == interface.lower()
            ssid = None
            connected = False
            continue
        if not in_iface:
            continue
        if re.match(r"^State\s*:\s+connected", stripped, re.IGNORECASE):
            connected = True
        m = re.match(r"^SSID\s*:\s+(.+)$", stripped)
        if m:
            ssid = m.group(1).strip()

    if connected and ssid:
        return ssid
    return None
