#!/usr/bin/env python3
"""
Universal 1-Click Installer & Launcher for Content Studio (Windows, macOS & Linux).

Uses only the Python 3.10+ standard library. Configures native Desktop/Menu
launchers, registers background auto-start, ensures the server is running on
http://127.0.0.1:8765/, and opens Content Studio in the browser.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import socket
import struct
import subprocess
import sys
import time
import webbrowser
import xml.sax.saxutils as xml_esc
import zlib
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PORT = 8765
URL = f"http://127.0.0.1:{PORT}/"


def is_server_running(port: int = PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.3):
            return True
    except OSError:
        return False


def _render_cs_rgba(size: int = 64) -> bytes:
    """Render an anti-aliased 64x64 RGBA Content Studio ('CS') badge using stdlib only."""
    # Bold 5x7 pixel bitmaps for 'C' and 'S'
    glyph_c = [
        "01110",
        "11011",
        "11000",
        "11000",
        "11000",
        "11011",
        "01110",
    ]
    glyph_s = [
        "01111",
        "11000",
        "11000",
        "01110",
        "00011",
        "00011",
        "11110",
    ]

    def in_glyph(bitmap: list[str], gx: float, gy: float) -> bool:
        if 0.0 <= gx < 5.0 and 0.0 <= gy < 7.0:
            return bitmap[int(gy)][int(gx)] == "1"
        return False

    raw = bytearray()
    cx = cy = (size - 1) / 2.0
    half = size / 2.0 - 1.0
    radius = 15.0
    scale = 4.2  # 5*4.2=21px wide, 7*4.2=29.4px tall

    for y in range(size):
        raw.append(0)  # PNG filter type 0
        for x in range(size):
            # Rounded-rectangle signed distance
            dx = max(abs(x - cx) - (half - radius), 0.0)
            dy = max(abs(y - cy) - (half - radius), 0.0)
            dist = (dx * dx + dy * dy) ** 0.5 - radius

            if dist > 0.8:
                raw.extend((0, 0, 0, 0))
                continue

            alpha = 255 if dist <= -0.5 else max(0, min(255, int((0.8 - dist) / 1.3 * 255)))
            t = (x + y) / (2.0 * (size - 1))
            r = int(45 + (10 - 45) * t)
            g = int(140 + (102 - 140) * t)
            b = int(255 + (194 - 255) * t)

            # Center "C" on left and "S" on right
            in_c = in_glyph(glyph_c, (x - 10.0) / scale, (y - 17.5) / scale)
            in_s = in_glyph(glyph_s, (x - 33.5) / scale, (y - 17.5) / scale)
            if in_c or in_s:
                r, g, b = 255, 255, 255

            raw.extend((r, g, b, alpha))
    return bytes(raw)


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    chunk = tag + data
    return struct.pack(">I", len(data)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)


def ensure_windows_ico() -> Path:
    """Create a PNG-backed Windows .ico at web/icon.ico using only Python stdlib."""
    ico_path = APP_DIR / "web" / "icon.ico"
    if ico_path.is_file() and ico_path.stat().st_size > 100:
        return ico_path

    size = 64
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    idat = zlib.compress(_render_cs_rgba(size), level=9)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )

    # Standard ICO header (1 image, PNG payload starting at offset 22)
    ico_bytes = (
        struct.pack("<HHH", 0, 1, 1)
        + struct.pack("<BBBBHHII", size, size, 0, 0, 1, 32, len(png_bytes), 22)
        + png_bytes
    )
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    ico_path.write_bytes(ico_bytes)
    return ico_path


def _run_quiet(cmd: list[str]) -> None:
    try:
        subprocess.run(cmd, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def install_linux() -> None:
    launch_sh = APP_DIR / "launch.sh"
    if launch_sh.is_file():
        os.chmod(launch_sh, 0o755)

    python_bin = shutil.which("python3") or sys.executable
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)
    service_path = service_dir / "linkedin-content-studio.service"
    service_path.write_text(
        f"""[Unit]
Description=Content Studio Local Web Server
After=network.target

[Service]
Type=simple
WorkingDirectory="{APP_DIR}"
ExecStart="{python_bin}" "{APP_DIR / "studio.py"}" --host 127.0.0.1 --port {PORT}
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
""",
        encoding="utf-8",
    )
    _run_quiet(["systemctl", "--user", "daemon-reload"])
    _run_quiet(["systemctl", "--user", "enable", "--now", "linkedin-content-studio.service"])
    _run_quiet(["systemctl", "--user", "restart", "linkedin-content-studio.service"])

    desktop_content = f"""[Desktop Entry]
Version=1.0
Type=Application
Name=Content Studio
Comment=Text & Markdown Social Content Studio
Exec="{launch_sh}"
Path={APP_DIR}
Icon={APP_DIR / "web" / "icon.svg"}
Terminal=false
Categories=Utility;
StartupNotify=false
"""
    apps_dir = Path.home() / ".local" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    app_desktop = apps_dir / "linkedin-content-studio.desktop"
    app_desktop.write_text(desktop_content, encoding="utf-8")
    os.chmod(app_desktop, 0o755)

    desktop_dir = Path.home() / "Desktop"
    if desktop_dir.is_dir():
        desk_file = desktop_dir / "linkedin-content-studio.desktop"
        desk_file.write_text(desktop_content, encoding="utf-8")
        os.chmod(desk_file, 0o755)
        _run_quiet(["gio", "set", str(desk_file), "metadata::trusted", "true"])

    _run_quiet(["update-desktop-database", str(apps_dir)])
    print(f"[ok] Installed Linux service & shortcuts for {APP_DIR}")


def _ps_quote(val: str) -> str:
    return val.replace("'", "''")


def install_windows() -> None:
    ico_path = ensure_windows_ico()
    exe_dir = Path(sys.executable).resolve().parent
    pythonw = exe_dir / "pythonw.exe"
    if not pythonw.is_file():
        pythonw = Path(shutil.which("pythonw") or sys.executable)

    vbs_path = APP_DIR / "launch-windows.vbs"
    vbs_path.write_text(
        f'Set WshShell = CreateObject("WScript.Shell")\n'
        f'WshShell.CurrentDirectory = "{APP_DIR}"\n'
        f'WshShell.Run """{pythonw}"" ""{APP_DIR / "install.py"}"" --launch-only", 0, False\n',
        encoding="utf-8",
    )

    ps_script = f"""
$ws = New-Object -ComObject WScript.Shell
$targets = @(
  (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Content Studio.lnk'),
  (Join-Path ([Environment]::GetFolderPath('Programs')) 'Content Studio.lnk')
)
foreach ($lnkPath in $targets) {{
  $s = $ws.CreateShortcut($lnkPath)
  $s.TargetPath = 'wscript.exe'
  $s.Arguments = '"{_ps_quote(str(vbs_path))}"'
  $s.WorkingDirectory = '{_ps_quote(str(APP_DIR))}'
  $s.IconLocation = '{_ps_quote(str(ico_path))},0'
  $s.Description = 'Launch Content Studio'
  $s.Save()
}}
$startupLnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Content Studio Server.lnk'
$st = $ws.CreateShortcut($startupLnk)
$st.TargetPath = '{_ps_quote(str(pythonw))}'
$st.Arguments = '"{_ps_quote(str(APP_DIR / "studio.py"))}" --host 127.0.0.1 --port {PORT}'
$st.WorkingDirectory = '{_ps_quote(str(APP_DIR))}'
$st.IconLocation = '{_ps_quote(str(ico_path))},0'
$st.WindowStyle = 7
$st.Save()
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        check=True,
    )
    print(f"[ok] Installed Windows Desktop, Start Menu, and Startup shortcuts for {APP_DIR}")


def install_macos() -> None:
    python_bin = shutil.which("python3") or sys.executable
    apps_dir = Path.home() / "Applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir = apps_dir / "Content Studio.app"
    macos_dir = bundle_dir / "Contents" / "MacOS"
    macos_dir.mkdir(parents=True, exist_ok=True)

    (bundle_dir / "Contents" / "Info.plist").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Content Studio</string>
  <key>CFBundleDisplayName</key><string>Content Studio</string>
  <key>CFBundleIdentifier</key><string>com.contentstudio.app</string>
  <key>CFBundleVersion</key><string>1.0</string>
  <key>CFBundleExecutable</key><string>ContentStudio</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSUIElement</key><false/>
</dict>
</plist>
""",
        encoding="utf-8",
    )

    launcher = macos_dir / "ContentStudio"
    launcher.write_text(
        f"""#!/usr/bin/env bash
"{python_bin}" "{APP_DIR / "install.py"}" --launch-only
""",
        encoding="utf-8",
    )
    os.chmod(launcher, 0o755)

    desktop_dir = Path.home() / "Desktop"
    if desktop_dir.is_dir():
        desk_app = desktop_dir / "Content Studio.app"
        if desk_app.exists() or desk_app.is_symlink():
            if desk_app.is_symlink():
                desk_app.unlink()
            elif desk_app.is_dir():
                shutil.rmtree(desk_app)
        shutil.copytree(bundle_dir, desk_app)

    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)
    plist_path = agents_dir / "com.contentstudio.server.plist"
    app_xml = xml_esc.escape(str(APP_DIR))
    py_xml = xml_esc.escape(str(python_bin))
    studio_xml = xml_esc.escape(str(APP_DIR / "studio.py"))
    plist_path.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.contentstudio.server</string>
  <key>ProgramArguments</key>
  <array>
    <string>{py_xml}</string>
    <string>{studio_xml}</string>
    <string>--host</string>
    <string>127.0.0.1</string>
    <string>--port</string>
    <string>{PORT}</string>
  </array>
  <key>WorkingDirectory</key><string>{app_xml}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
""",
        encoding="utf-8",
    )
    _run_quiet(["launchctl", "unload", str(plist_path)])
    _run_quiet(["launchctl", "load", "-w", str(plist_path)])
    print(f"[ok] Installed macOS App Bundle & LaunchAgent for {APP_DIR}")


def ensure_started_and_open(open_browser: bool = True) -> None:
    if not is_server_running():
        cmd = [sys.executable, str(APP_DIR / "studio.py"), "--host", "127.0.0.1", "--port", str(PORT)]
        kwargs: dict[str, object] = {
            "cwd": str(APP_DIR),
            "stdin": subprocess.DEVNULL,
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
        }
        if platform.system() == "Windows":
            exe_dir = Path(sys.executable).resolve().parent
            pyw = exe_dir / "pythonw.exe"
            if pyw.is_file():
                cmd[0] = str(pyw)
            kwargs["creationflags"] = (
                getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            )
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen(cmd, **kwargs)  # type: ignore[arg-type]

        for _ in range(40):
            if is_server_running():
                break
            time.sleep(0.1)

    if open_browser:
        webbrowser.open(URL)


def main() -> int:
    parser = argparse.ArgumentParser(description="1-Click Cross-Platform Installer for Content Studio")
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser window")
    parser.add_argument("--launch-only", action="store_true", help="Skip desktop registration; start and open UI")
    args = parser.parse_args()

    if not args.launch_only:
        ensure_windows_ico()
        system = platform.system()
        if system == "Linux":
            install_linux()
        elif system == "Windows":
            install_windows()
        elif system == "Darwin":
            install_macos()
        else:
            print(f"[warn] Unknown OS '{system}'; starting server directly.")

    ensure_started_and_open(open_browser=not args.no_open)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
