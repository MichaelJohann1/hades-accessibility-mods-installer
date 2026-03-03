"""
Hades Accessibility Mods Installer v1.2
Downloads the latest mod files from GitHub and installs them to the Hades game directory.
"""

import os
import sys
import ctypes
import urllib.request
import json
import threading
import winreg
import string
import wx

# Installer version
INSTALLER_VERSION = "1.2"

# GitHub repo info
GITHUB_REPO = "MichaelJohann1/hades-accessibility-mods"
GITHUB_BRANCH = "main"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/"
GITHUB_API_RELEASES = f"https://api.github.com/repos/{GITHUB_REPO}/releases"

# Files to download and install to x64 folder
INSTALL_FILES = [
    "xinput1_4.dll",
    "Tolk.dll",
    "nvdaControllerClient64.dll",
]

# Extra files (for saving to installer folder)
README_FILE = "readme.html"
CHANGELOG_FILE = "changelog.txt"

# Installer exe name on GitHub releases
INSTALLER_EXE_NAME = "HadesAccessibilityInstaller.exe"


def _load_nvda():
    """Try to load NVDA controller client for speech output."""
    try:
        # Try bundled path first (PyInstaller)
        if getattr(sys, '_MEIPASS', None):
            dll_path = os.path.join(sys._MEIPASS, "nvdaControllerClient64.dll")
            if os.path.isfile(dll_path):
                lib = ctypes.windll.LoadLibrary(dll_path)
                if lib.nvdaController_testIfRunning() == 0:
                    return lib
        # Try system/PATH
        lib = ctypes.windll.LoadLibrary("nvdaControllerClient64")
        if lib.nvdaController_testIfRunning() == 0:
            return lib
    except (OSError, AttributeError):
        pass
    return None


_nvda = _load_nvda()


def nvda_speak(text):
    """Speak text through NVDA if available."""
    if _nvda:
        try:
            _nvda.nvdaController_speakText(text)
        except Exception:
            pass


def find_steam_libraries():
    """Find all Steam library folders from the registry and libraryfolders.vdf."""
    libraries = []

    # Try to get the main Steam install path from the registry
    steam_path = None
    for key_path in [r"SOFTWARE\Valve\Steam", r"SOFTWARE\WOW6432Node\Valve\Steam"]:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                steam_path, _ = winreg.QueryValueEx(key, "InstallPath")
                break
        except (OSError, FileNotFoundError):
            pass

    if not steam_path:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam") as key:
                steam_path, _ = winreg.QueryValueEx(key, "SteamPath")
        except (OSError, FileNotFoundError):
            pass

    if steam_path:
        libraries.append(os.path.join(steam_path, "steamapps", "common"))

        # Parse libraryfolders.vdf for additional library paths
        vdf_path = os.path.join(steam_path, "steamapps", "libraryfolders.vdf")
        if os.path.isfile(vdf_path):
            try:
                with open(vdf_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if '"path"' in line:
                            parts = line.split('"')
                            if len(parts) >= 4:
                                lib_path = parts[3].replace("\\\\", "\\")
                                common = os.path.join(lib_path, "steamapps", "common")
                                if common not in libraries:
                                    libraries.append(common)
            except Exception:
                pass

    # Also check common default locations as fallback
    for path in [
        r"C:\Program Files (x86)\Steam\steamapps\common",
        r"C:\Program Files\Steam\steamapps\common",
    ]:
        if path not in libraries:
            libraries.append(path)

    # Check all drive letters for Steam libraries
    for letter in string.ascii_uppercase:
        for steam_dir in [
            f"{letter}:\\SteamLibrary\\steamapps\\common",
            f"{letter}:\\Steam\\steamapps\\common",
            f"{letter}:\\Program Files (x86)\\Steam\\steamapps\\common",
        ]:
            if steam_dir not in libraries:
                libraries.append(steam_dir)

    return libraries


def find_game_directory():
    """Search for Hades.exe across all Steam libraries and return the game directory."""
    for common_dir in find_steam_libraries():
        hades_dir = os.path.join(common_dir, "Hades")
        hades_exe = os.path.join(hades_dir, "x64", "Hades.exe")
        if os.path.isfile(hades_exe):
            return hades_dir
    return ""


def get_installer_dir():
    """Get the directory where the installer is located."""
    if getattr(sys, 'frozen', False):
        # Running as PyInstaller bundle
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.abspath(sys.argv[0]))


def get_installer_path():
    """Get the full path of the current installer executable."""
    if getattr(sys, 'frozen', False):
        return sys.executable
    else:
        return os.path.abspath(sys.argv[0])


def check_for_installer_update():
    """Check GitHub releases for a newer installer version.
    Returns (new_version, download_url) if update available, else (None, None).
    """
    try:
        req = urllib.request.Request(
            GITHUB_API_RELEASES,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "HadesAccessibilityInstaller"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            releases = json.loads(resp.read().decode("utf-8"))

        for release in releases:
            tag = release.get("tag_name", "")
            # Only look at installer-tagged releases (e.g. "installer-1.2")
            # Skip all other releases (mod releases like "v34", "v34.1.1", etc.)
            if not tag.startswith("installer-"):
                continue
            remote_version = tag.replace("installer-", "", 1)

            if _version_newer(remote_version, INSTALLER_VERSION):
                # Find the exe asset
                for asset in release.get("assets", []):
                    if asset["name"].lower() == INSTALLER_EXE_NAME.lower():
                        return remote_version, asset["browser_download_url"]
        return None, None
    except Exception:
        return None, None


def _version_newer(remote, local):
    """Return True if remote version is newer than local version."""
    try:
        remote_parts = [int(x) for x in remote.split(".")]
        local_parts = [int(x) for x in local.split(".")]
        return remote_parts > local_parts
    except (ValueError, AttributeError):
        return False


class InstallerFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title=f"Hades Accessibility Mods Installer v{INSTALLER_VERSION}", style=wx.DEFAULT_FRAME_STYLE & ~(wx.RESIZE_BORDER | wx.MAXIMIZE_BOX))

        self.game_dir = find_game_directory()
        self.installed = False
        self.game_x64_dir = ""

        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)

        # Select Folder label
        label = wx.StaticText(panel, label="Select Folder:")
        main_sizer.Add(label, 0, wx.LEFT | wx.TOP, 10)

        # Path field + Browse button
        path_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.dir_text = wx.TextCtrl(panel, value=self.game_dir, size=(400, -1))
        path_sizer.Add(self.dir_text, 1, wx.EXPAND)
        self.browse_btn = wx.Button(panel, label="Browse for Folder...")
        path_sizer.Add(self.browse_btn, 0, wx.LEFT, 5)
        main_sizer.Add(path_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

        # Checkboxes
        self.readme_cb = wx.CheckBox(panel, label="Save readme to installer folder")
        main_sizer.Add(self.readme_cb, 0, wx.LEFT | wx.TOP, 10)

        self.changelog_cb = wx.CheckBox(panel, label="Save changelog to installer folder")
        main_sizer.Add(self.changelog_cb, 0, wx.LEFT | wx.TOP, 5)

        # Buttons
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.install_btn = wx.Button(panel, label="Install Hades Mods")
        btn_sizer.Add(self.install_btn, 0)
        self.log_btn = wx.Button(panel, label="Open Debug Log Folder")
        self.log_btn.Disable()
        btn_sizer.Add(self.log_btn, 0, wx.LEFT, 5)
        self.exit_btn = wx.Button(panel, label="Exit")
        btn_sizer.Add(self.exit_btn, 0, wx.LEFT, 5)
        main_sizer.Add(btn_sizer, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 10)

        # Log area (read-only)
        self.log_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP, size=(500, 250))
        main_sizer.Add(self.log_text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        panel.SetSizer(main_sizer)
        main_sizer.Fit(self)

        # Bind events
        self.browse_btn.Bind(wx.EVT_BUTTON, self.on_browse)
        self.install_btn.Bind(wx.EVT_BUTTON, self.on_install)
        self.log_btn.Bind(wx.EVT_BUTTON, self.on_open_debug_log_folder)
        self.exit_btn.Bind(wx.EVT_BUTTON, self.on_exit)

        self.Centre()

    def log(self, message):
        """Append a message to the log area (thread-safe)."""
        wx.CallAfter(self._log, message)

    def _log(self, message):
        self.log_text.AppendText(message + "\n")
        nvda_speak(message)

    def on_browse(self, event):
        dlg = wx.DirDialog(self, "Select Hades Game Directory", style=wx.DD_DEFAULT_STYLE)
        if dlg.ShowModal() == wx.ID_OK:
            self.dir_text.SetValue(dlg.GetPath())
        dlg.Destroy()

    def on_install(self, event):
        game_dir = self.dir_text.GetValue().strip()
        if not game_dir:
            self.log("Error: Please select the Hades game directory.")
            return

        x64_dir = os.path.join(game_dir, "x64")

        # Maybe they selected the x64 folder directly
        if not os.path.isdir(x64_dir):
            if os.path.basename(game_dir).lower() == "x64":
                x64_dir = game_dir
                game_dir = os.path.dirname(game_dir)
            else:
                self.log("Error: Could not find the x64 folder in the selected directory.")
                self.log("Please select the Hades game directory (e.g. Steam\\steamapps\\common\\Hades).")
                return

        # Check for Hades.exe
        hades_exe = os.path.join(x64_dir, "Hades.exe")
        if not os.path.isfile(hades_exe):
            result = wx.MessageBox(
                "Hades.exe was not found in the x64 folder.\nAre you sure this is the correct Hades directory?",
                "Warning", wx.YES_NO | wx.ICON_WARNING, self)
            if result != wx.YES:
                return

        self.game_x64_dir = x64_dir
        self.install_btn.Disable()
        self.log("Starting installation...")
        self.log(f"Target: {x64_dir}")

        # Run install in a thread so the UI doesn't freeze
        thread = threading.Thread(target=self.install, args=(x64_dir,), daemon=True)
        thread.start()

    def install(self, x64_dir):
        """Download files from GitHub and install."""
        errors = []
        copied = 0
        installer_dir = get_installer_dir()

        try:
            # Download and install DLL files
            for filename in INSTALL_FILES:
                try:
                    self.log(f"Downloading {filename}...")
                    dest = os.path.join(x64_dir, filename)
                    download_url = GITHUB_RAW_BASE + filename
                    urllib.request.urlretrieve(download_url, dest)
                    copied += 1
                    self.log(f"  {filename} installed.")
                except PermissionError:
                    msg = f"Permission denied writing {filename}. Is Hades running? Close the game and try again."
                    errors.append(msg)
                    self.log(f"  Error: {msg}")
                except urllib.error.URLError as e:
                    msg = f"Failed to download {filename}: {e}"
                    errors.append(msg)
                    self.log(f"  Error: {msg}")
                except Exception as e:
                    msg = f"Error installing {filename}: {e}"
                    errors.append(msg)
                    self.log(f"  Error: {msg}")

            # Save readme to installer folder if checked
            if self.readme_cb.GetValue():
                try:
                    self.log("Saving readme...")
                    dest = os.path.join(installer_dir, README_FILE)
                    urllib.request.urlretrieve(GITHUB_RAW_BASE + README_FILE, dest)
                    self.log(f"  Readme saved to {installer_dir}")
                except Exception as e:
                    msg = f"Failed to save readme: {e}"
                    errors.append(msg)
                    self.log(f"  Error: {msg}")

            # Save changelog to installer folder if checked
            if self.changelog_cb.GetValue():
                try:
                    self.log("Saving changelog...")
                    dest = os.path.join(installer_dir, CHANGELOG_FILE)
                    urllib.request.urlretrieve(GITHUB_RAW_BASE + CHANGELOG_FILE, dest)
                    self.log(f"  Changelog saved to {installer_dir}")
                except Exception as e:
                    msg = f"Failed to save changelog: {e}"
                    errors.append(msg)
                    self.log(f"  Error: {msg}")

        except Exception as e:
            errors.append(f"Unexpected error: {e}")

        # Update UI on main thread
        def finish():
            self.install_btn.Enable()
            if errors:
                self.log(f"\nInstallation completed with errors. {copied}/{len(INSTALL_FILES)} files installed.")
            else:
                self.log(f"\nInstallation complete! {copied} files installed to {x64_dir}")
                self.installed = True
                self.log_btn.Enable()

        wx.CallAfter(finish)

    def on_open_debug_log_folder(self, event):
        if not self.installed:
            self.log("Error: Please install the mods first.")
            return

        logs_dir = os.path.join(self.game_x64_dir, "logs")
        if not os.path.isdir(logs_dir):
            self.log("Debug log folder not found. Run Hades with the mods installed first to generate logs.")
            return

        try:
            os.startfile(logs_dir)
            self.log(f"Opened debug log folder: {logs_dir}")
        except Exception as e:
            self.log(f"Error: Failed to open log folder: {e}")

    def on_exit(self, event):
        self.Close()


def download_update(download_url, new_version):
    """Download new installer next to the current one.
    Returns the path to the downloaded file, or None on failure.
    """
    installer_dir = get_installer_dir()
    new_exe_path = os.path.join(installer_dir, f"HadesAccessibilityInstaller_v{new_version}.exe")

    try:
        urllib.request.urlretrieve(download_url, new_exe_path)
        # Verify the download is a real exe (PE header starts with MZ)
        with open(new_exe_path, "rb") as f:
            header = f.read(2)
        if header != b"MZ":
            os.remove(new_exe_path)
            return None
        return new_exe_path
    except Exception:
        if os.path.isfile(new_exe_path):
            try:
                os.remove(new_exe_path)
            except Exception:
                pass
        return None


def schedule_self_delete():
    """Schedule deletion of the current exe after the process exits using a batch script."""
    if not getattr(sys, 'frozen', False):
        return
    import subprocess
    current_exe = sys.executable
    installer_dir = os.path.dirname(current_exe)
    bat_path = os.path.join(installer_dir, "_cleanup.bat")
    try:
        with open(bat_path, "w") as bat:
            bat.write("@echo off\n")
            bat.write("timeout /t 2 /nobreak >nul\n")
            bat.write(f'del /f "{current_exe}"\n')
            bat.write(f'del /f "%~f0"\n')
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            creationflags=0x08000000,
            close_fds=True
        )
    except Exception:
        pass


def main():
    app = wx.App()

    # Check for installer updates
    nvda_speak("Checking for installer updates...")
    new_version, download_url = check_for_installer_update()
    if new_version and download_url:
        result = wx.MessageBox(
            f"A new version of the installer is available (v{new_version}).\n"
            f"You are currently running v{INSTALLER_VERSION}.\n\n"
            f"Would you like to download it now?",
            "Installer Update Available",
            wx.YES_NO | wx.ICON_INFORMATION
        )
        if result == wx.YES:
            nvda_speak(f"Downloading installer version {new_version}...")
            new_path = download_update(download_url, new_version)
            if new_path:
                nvda_speak("Download complete.")
                wx.MessageBox(
                    f"Installer v{new_version} has been downloaded.\n\n"
                    f"This installer will now close and the old version will be removed.",
                    "Update Downloaded",
                    wx.OK | wx.ICON_INFORMATION
                )
                schedule_self_delete()
                sys.exit(0)
            else:
                wx.MessageBox(
                    "Failed to download the update. Continuing with current version.",
                    "Update Error",
                    wx.OK | wx.ICON_WARNING
                )

    frame = InstallerFrame()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
