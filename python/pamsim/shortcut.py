"""Create "PAMsim" shortcuts that start the GUI with a double-click.

    python -m pamsim.shortcut

Windows: Desktop and Start menu shortcuts (with icon, no console window).
macOS: PAMsim.command on the Desktop.  Linux: application menu entry and a
launcher on the Desktop.
"""
import os
import stat
import subprocess
import sys

PKG = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(PKG)                     # the "python" folder
LAUNCHER = os.path.join(ROOT, "PAMsim.pyw")
ASSETS = os.path.join(PKG, "assets")


def _ps_quote(text):
    return "'" + str(text).replace("'", "''") + "'"


def windows():
    exe_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(exe_dir, "pythonw.exe")
    target = pythonw if os.path.exists(pythonw) else sys.executable
    ps = f"""
$ws = New-Object -ComObject WScript.Shell
$made = @()
foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {{
  if (-not $dir) {{ continue }}
  $link = Join-Path $dir 'PAMsim.lnk'
  $s = $ws.CreateShortcut($link)
  $s.TargetPath = {_ps_quote(target)}
  $s.Arguments = {_ps_quote('"' + LAUNCHER + '"')}
  $s.WorkingDirectory = {_ps_quote(ROOT)}
  $s.IconLocation = {_ps_quote(os.path.join(ASSETS, 'pamsim.ico'))}
  $s.Description = 'PAMsim - photon simulation for PAM'
  $s.Save()
  $made += $link
}}
$made
"""
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                         check=True, capture_output=True, text=True)
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def macos():
    path = os.path.join(os.path.expanduser("~"), "Desktop", "PAMsim.command")
    with open(path, "w") as f:
        f.write(f'#!/bin/bash\ncd "{ROOT}"\n"{sys.executable}" "{LAUNCHER}"\n')
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return [path]


def linux():
    entry = (f"[Desktop Entry]\nType=Application\nName=PAMsim\nComment=Photon simulation for PAM\n"
             f'Exec="{sys.executable}" "{LAUNCHER}"\nPath={ROOT}\nIcon={os.path.join(ASSETS, "pamsim.png")}\n'
             f"Terminal=false\nCategories=Science;Education;\n")
    made = []
    for d in (os.path.join(os.path.expanduser("~"), ".local", "share", "applications"),
              os.path.join(os.path.expanduser("~"), "Desktop")):
        if os.path.isdir(os.path.dirname(d)) or d.endswith("applications"):
            os.makedirs(d, exist_ok=True)
            p = os.path.join(d, "pamsim.desktop")
            with open(p, "w") as f:
                f.write(entry)
            os.chmod(p, os.stat(p).st_mode | stat.S_IXUSR)
            made.append(p)
    return made


def main():
    if sys.platform == "win32":
        made = windows()
    elif sys.platform == "darwin":
        made = macos()
    else:
        made = linux()
    for p in made:
        print("created", p)
    return made


if __name__ == "__main__":
    main()
