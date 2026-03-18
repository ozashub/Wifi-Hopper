#!/usr/bin/env python3
import argparse
import ctypes
import os
import sys
import time
import traceback

from wifi_hopper.config import HopperConfig
from wifi_hopper.hopper import Hopper
from wifi_hopper.logger import setup_logger
from wifi_hopper import scanner


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except AttributeError:
        return False


SW_SHOWNORMAL = 1


def _relaunch_as_admin() -> None:
    script = os.path.abspath(__file__)
    args = " ".join(f'"{a}"' for a in sys.argv[1:])
    ret = ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, f'"{script}" {args}', None, SW_SHOWNORMAL
    )
    if ret <= 32:
        print(f"UAC elevation failed (code {ret}). Run as Administrator manually.")
        input("Press Enter to exit...")
        sys.exit(1)
    sys.exit(0)


def _ensure_elevated() -> None:
    if not _is_admin():
        print("Requesting admin elevation...")
        _relaunch_as_admin()


def cmd_scan(args) -> None:
    setup_logger(args.log)
    iface = args.interface or _auto_interface()
    print(f"Scanning on interface: {iface}\n")

    try:
        networks = scanner.scan_open_networks(iface)
    except RuntimeError as exc:
        print(f"Scan failed: {exc}")
        sys.exit(1)

    if not networks:
        print("No open (passwordless) networks found.")
        return

    print(f"{'SSID':<35} {'Signal':>7}  {'Ch':>3}  Radio")
    print("-" * 65)
    for n in sorted(networks, key=lambda x: x.signal, reverse=True):
        print(f"{n.ssid:<35} {n.signal:>6}%  {n.channel:>3}  {n.radio_type}")


def cmd_status(args) -> None:
    iface = args.interface or _auto_interface()
    ssid = scanner.get_connected_ssid(iface)
    if ssid:
        print(f"Connected: {ssid!r}  ({iface})")
    else:
        print(f"Not connected  ({iface})")


def cmd_start(args) -> None:
    setup_logger(args.log)
    blacklist = [s.strip() for s in args.blacklist.split(",")] if args.blacklist else []
    iface = args.interface or _auto_interface()

    cfg = HopperConfig(
        poll_interval=args.interval,
        interface=iface,
        log_file=args.log,
        blacklist=blacklist,
        min_signal=args.min_signal,
        dwell_time=args.dwell,
        dry_run=args.dry_run,
        disconnect_on_exit=args.disconnect_on_exit,
    )

    hopper = Hopper(cfg)
    hopper.start()

    try:
        while hopper.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nShutting down...")
        hopper.stop()
        hopper.join(timeout=15)


def _auto_interface() -> str:
    try:
        return scanner.get_interface_name()
    except RuntimeError as exc:
        print(f"Error: {exc}")
        input("Press Enter to exit...")
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wifi-hopper",
        description="Lightweight background open-WiFi auto-connector.",
    )
    p.add_argument("--interface", "-i", default=None)
    p.add_argument("--log", default="wifi_hopper.log")

    sub = p.add_subparsers(dest="command")

    sub.add_parser("scan")
    sub.add_parser("status")

    sp = sub.add_parser("start")
    sp.add_argument("--interval", type=int, default=3)
    sp.add_argument("--min-signal", type=int, default=0)
    sp.add_argument("--dwell", type=int, default=120)
    sp.add_argument("--blacklist", default="")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--disconnect-on-exit", action="store_true")

    return p


def main() -> None:
    _ensure_elevated()

    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        # no subcommand given — default to start with all defaults
        args = parser.parse_args(["start"])

    dispatch = {
        "scan":   cmd_scan,
        "status": cmd_status,
        "start":  cmd_start,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        input("\nCrashed. Press Enter to exit...")
