import subprocess
import tempfile
import time
import os
import re
import logging

log = logging.getLogger("wifi_hopper")

_PROFILE_TEMPLATE = """\
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
  <name>{ssid}</name>
  <SSIDConfig>
    <SSID>
      <name>{ssid}</name>
    </SSID>
  </SSIDConfig>
  <connectionType>ESS</connectionType>
  <connectionMode>manual</connectionMode>
  <MSM>
    <security>
      <authEncryption>
        <authentication>open</authentication>
        <encryption>none</encryption>
        <useOneX>false</useOneX>
      </authEncryption>
    </security>
  </MSM>
</WLANProfile>
"""

_CONNECT_TIMEOUT = 12   # seconds to wait for confirmed connection
_CONNECT_POLL    = 0.8  # seconds between state polls


def install_open_profile(ssid: str, interface: str) -> bool:
    """Write a temp XML profile for an open network and load it into Windows."""
    xml = _PROFILE_TEMPLATE.format(ssid=_escape_xml(ssid))

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".xml", delete=False, encoding="utf-8"
        ) as f:
            f.write(xml)
            tmp_path = f.name

        result = subprocess.run(
            ["netsh", "wlan", "add", "profile", f"filename={tmp_path}",
             f"interface={interface}", "user=current"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            log.debug("add profile stderr: %s", result.stderr.strip())
            return False
        return True
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log.warning("install_open_profile failed: %s", exc)
        return False
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def connect_to_network(ssid: str, interface: str) -> bool:
    """Issue netsh connect and poll until confirmed connected or timeout."""
    result = subprocess.run(
        ["netsh", "wlan", "connect", f"name={ssid}", f"ssid={ssid}", f"interface={interface}"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        log.debug("connect cmd failed: %s", result.stderr.strip())
        return False

    deadline = time.monotonic() + _CONNECT_TIMEOUT
    while time.monotonic() < deadline:
        time.sleep(_CONNECT_POLL)
        connected_ssid = _query_connected_ssid(interface)
        if connected_ssid and connected_ssid.lower() == ssid.lower():
            return True

    return False


def disconnect(interface: str, ssid: str | None = None) -> None:
    """Disconnect from current network and clean up profile if ssid is given."""
    subprocess.run(
        ["netsh", "wlan", "disconnect", f"interface={interface}"],
        capture_output=True,
        timeout=10,
    )
    if ssid:
        delete_profile(ssid, interface)


def delete_profile(ssid: str, interface: str) -> None:
    """Remove the named profile from Windows to avoid leftover clutter."""
    try:
        subprocess.run(
            ["netsh", "wlan", "delete", "profile", f"name={ssid}", f"interface={interface}"],
            capture_output=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass


def _query_connected_ssid(interface: str) -> str | None:
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    in_iface = False
    ssid = None
    for line in result.stdout.splitlines():
        stripped = line.strip()
        if re.match(r"^Name\s*:", stripped):
            iface_name = stripped.split(":", 1)[1].strip()
            in_iface = iface_name.lower() == interface.lower()
            continue
        if not in_iface:
            continue
        m = re.match(r"^SSID\s*:\s+(.+)$", stripped)
        if m:
            ssid = m.group(1).strip()
        if re.match(r"^State\s*:\s+connected", stripped, re.IGNORECASE):
            return ssid

    return None


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
    )
