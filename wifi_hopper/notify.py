import os
import subprocess

_PS = (
    "Add-Type -AssemblyName System.Windows.Forms;"
    "$n=[System.Windows.Forms.NotifyIcon]::new();"
    "$n.Icon=[System.Drawing.SystemIcons]::Network;"
    "$n.Visible=$true;"
    "$n.ShowBalloonTip(4000,$env:N_TITLE,$env:N_BODY,"
    "[System.Windows.Forms.ToolTipIcon]::None);"
    "Start-Sleep 5;$n.Dispose()"
)


def toast(title: str, body: str) -> None:
    subprocess.Popen(
        ["powershell", "-WindowStyle", "Hidden", "-Command", _PS],
        env={**os.environ, "N_TITLE": title, "N_BODY": body},
        creationflags=subprocess.CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
