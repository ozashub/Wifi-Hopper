import threading
import time
import logging
from enum import Enum, auto

from .config import HopperConfig
from .scanner import scan_open_networks, get_connected_ssid, ping_ms
from .notify import toast
from .connector import install_open_profile, connect_to_network, disconnect, delete_profile

log = logging.getLogger("wifi_hopper")

_FAILED_TTL = 300


class State(Enum):
    IDLE       = auto()
    SCANNING   = auto()
    CONNECTING = auto()
    CONNECTED  = auto()
    FAILED     = auto()


class Hopper(threading.Thread):

    def __init__(self, config: HopperConfig):
        super().__init__(name="wifi-hopper", daemon=True)
        self._cfg = config
        self._stop_event = threading.Event()
        self._state = State.IDLE
        self._current_ssid: str | None = None
        self._dwell_until: float = 0.0
        self._failed: dict[str, float] = {}
        self._latency: dict[str, float] = {}

    def stop(self) -> None:
        self._stop_event.set()

    @property
    def state(self) -> State:
        return self._state

    @property
    def current_ssid(self) -> str | None:
        return self._current_ssid

    def run(self) -> None:
        print(f"Hopper running  [poll={self._cfg.poll_interval}s  dwell={self._cfg.dwell_time}s"
              f"  dry_run={self._cfg.dry_run}]")
        print("Scanning for open networks...\n")

        while not self._stop_event.is_set():
            try:
                self._tick()
            except Exception as exc:
                print(f"Error: {exc}")
                log.error("hopper loop error: %s", exc, exc_info=True)
            self._stop_event.wait(self._cfg.poll_interval)

        if self._cfg.disconnect_on_exit and self._current_ssid:
            disconnect(self._cfg.interface, self._current_ssid)

    def _tick(self) -> None:
        self._state = State.SCANNING

        try:
            candidates = scan_open_networks(self._cfg.interface)
        except RuntimeError as exc:
            print(f"Scan failed: {exc}")
            self._state = State.IDLE
            return

        now = time.monotonic()
        self._failed = {s: t for s, t in self._failed.items() if t > now}

        candidates = [n for n in candidates if n.signal >= self._cfg.min_signal]
        candidates = [n for n in candidates if n.ssid not in self._cfg.blacklist]
        candidates = [n for n in candidates if n.ssid not in self._failed]

        if not candidates:
            if self._state != State.IDLE:
                print("No open networks found, still looking...")
            self._state = State.IDLE
            return

        known = sorted(
            [(n, self._latency[n.ssid]) for n in candidates if n.ssid in self._latency],
            key=lambda x: x[1],
        )
        unknown = sorted(
            [n for n in candidates if n.ssid not in self._latency],
            key=lambda n: n.signal, reverse=True,
        )
        best = ([n for n, _ in known] + unknown)[0]

        if self._current_ssid == best.ssid and now < self._dwell_until:
            self._state = State.CONNECTED
            return

        if self._current_ssid is not None and self._current_ssid != best.ssid:
            cur_lat = self._latency.get(self._current_ssid)
            best_lat = self._latency.get(best.ssid)
            if cur_lat is not None and best_lat is not None:
                # only hop if the gain is real, not just noise
                if cur_lat - best_lat < 20:
                    self._state = State.CONNECTED
                    return
            else:
                cur_sig = next((n.signal for n in candidates if n.ssid == self._current_ssid), 0)
                if cur_sig > 0 and best.signal - cur_sig < 15:
                    self._state = State.CONNECTED
                    return

        print(f"Found {len(candidates)} open network(s), trying {best.ssid} ({best.signal}% signal)...")
        self._connect(best)

    def _connect(self, network) -> None:
        self._state = State.CONNECTING

        if self._cfg.dry_run:
            log.info("[dry-run] would connect to %r", network.ssid)
            self._state = State.IDLE
            return

        if self._current_ssid and self._current_ssid != network.ssid:
            disconnect(self._cfg.interface, self._current_ssid)
            self._current_ssid = None

        t0 = time.monotonic()

        if not install_open_profile(network.ssid, self._cfg.interface):
            print(f"Couldn't set up profile for {network.ssid}, skipping")
            self._failed[network.ssid] = time.monotonic() + _FAILED_TTL
            return

        ok = connect_to_network(network.ssid, self._cfg.interface)
        elapsed = time.monotonic() - t0

        if ok:
            self._current_ssid = network.ssid
            self._dwell_until = time.monotonic() + self._cfg.dwell_time
            self._state = State.CONNECTED
            ms = ping_ms()
            if ms is not None:
                self._latency[network.ssid] = ms
            lat = f"{ms:.0f}ms" if ms is not None else "?"
            msg = f"Connected to: {network.ssid}  ({lat})"
            log.info("connected  ssid=%r  signal=%d%%  ch=%d  latency=%s  (%.1fs)",
                     network.ssid, network.signal, network.channel, lat, elapsed)
            print(msg)
            toast("WiFi Hopper", msg)
        else:
            self._state = State.FAILED
            self._failed[network.ssid] = time.monotonic() + _FAILED_TTL
            delete_profile(network.ssid, self._cfg.interface)
            msg = f"Failed to connect to: {network.ssid}"
            log.warning("connection to %r failed after %.1fs", network.ssid, elapsed)
            print(msg)
            toast("WiFi Hopper", msg)
