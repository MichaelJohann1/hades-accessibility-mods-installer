"""
Hades Accessibility Mods Installer v1.6
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
import zipfile
import tempfile
import webbrowser
import wx

# Installer version
INSTALLER_VERSION = "1.7"

# GitHub repo info
GITHUB_MOD_REPO = "MichaelJohann1/hades-accessibility-mods"
GITHUB_INSTALLER_REPO = "MichaelJohann1/hades-accessibility-mods-installer"
GITHUB_BRANCH = "main"
GITHUB_RAW_BASE = f"https://raw.githubusercontent.com/{GITHUB_MOD_REPO}/{GITHUB_BRANCH}/"
GITHUB_MOD_API_RELEASES = f"https://api.github.com/repos/{GITHUB_MOD_REPO}/releases"
GITHUB_INSTALLER_API_RELEASES = f"https://api.github.com/repos/{GITHUB_INSTALLER_REPO}/releases"
GITHUB_LICENSE_URL = f"https://github.com/{GITHUB_MOD_REPO}/blob/{GITHUB_BRANCH}/LICENSE.txt"
GITHUB_ORIGINAL_LICENSE_URL = f"https://github.com/{GITHUB_MOD_REPO}/blob/{GITHUB_BRANCH}/LICENSE-ORIGINAL.txt"

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

# Version tracking file in game's x64 directory
VERSION_FILE = ".mod_version"


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


def get_latest_mod_release():
    """Get the latest mod release from GitHub.
    Returns (tag, assets_dict, body) or (None, None, None).
    assets_dict maps filename -> download_url.
    The assets_dict may contain a special key '_zip_url' with the download URL
    for a HadesAccessibilityMods*.zip asset if one exists.
    """
    try:
        req = urllib.request.Request(
            GITHUB_MOD_API_RELEASES,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "HadesAccessibilityInstaller"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            releases = json.loads(resp.read().decode("utf-8"))

        for release in releases:
            tag = release.get("tag_name", "")
            # Skip installer-tagged releases
            if tag.startswith("installer-"):
                continue
            assets = {}
            for asset in release.get("assets", []):
                name = asset["name"]
                url = asset["browser_download_url"]
                assets[name] = url
                # Track zip asset specially
                if name.lower().startswith("hadesaccessibilitymods") and name.lower().endswith(".zip"):
                    assets["_zip_url"] = url
                    assets["_zip_name"] = name
            body = release.get("body", "")
            return tag, assets, body
        return None, None, None
    except Exception:
        return None, None, None


def get_installed_mod_version(x64_dir):
    """Read the installed mod version from the game directory."""
    version_file = os.path.join(x64_dir, VERSION_FILE)
    try:
        with open(version_file, "r") as f:
            return f.read().strip()
    except Exception:
        return None


def save_installed_mod_version(x64_dir, version):
    """Save the installed mod version to the game directory."""
    version_file = os.path.join(x64_dir, VERSION_FILE)
    try:
        with open(version_file, "w") as f:
            f.write(version)
    except Exception:
        pass


def _mod_version_newer(remote_tag, local_tag):
    """Return True if remote mod version is newer than local."""
    try:
        remote = tuple(int(x) for x in remote_tag.lstrip("v").split("."))
        local = tuple(int(x) for x in local_tag.lstrip("v").split("."))
        return remote > local
    except (ValueError, AttributeError):
        return remote_tag != local_tag


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


def remove_old_mod_files(game_dir, log_func):
    """Remove legacy mod files that are no longer needed.
    Since session 24, all Lua mods are embedded in the DLL. Old external mod files
    (Content/Mods/ folder, modimporter.py, mod.log) can cause conflicts if left behind
    (e.g. dual ModUtil versions causing game freezes on room transitions).
    """
    content_dir = os.path.join(game_dir, "Content")
    removed = []

    # Remove Content/Mods/ folder
    mods_dir = os.path.join(content_dir, "Mods")
    if os.path.isdir(mods_dir):
        try:
            import shutil
            shutil.rmtree(mods_dir)
            removed.append("Content/Mods/ folder")
        except Exception as e:
            log_func(f"  Warning: Could not remove Content/Mods/ folder: {e}")

    # Remove modimporter.py
    modimporter = os.path.join(content_dir, "modimporter.py")
    if os.path.isfile(modimporter):
        try:
            os.remove(modimporter)
            removed.append("modimporter.py")
        except Exception as e:
            log_func(f"  Warning: Could not remove modimporter.py: {e}")

    # Remove mod.log (generated by modimporter.py)
    mod_log = os.path.join(content_dir, "mod.log")
    if os.path.isfile(mod_log):
        try:
            os.remove(mod_log)
            removed.append("mod.log")
        except Exception as e:
            log_func(f"  Warning: Could not remove mod.log: {e}")

    return removed


def check_for_installer_update():
    """Check GitHub releases for a newer installer version.
    Returns (new_version, download_url) if update available, else (None, None).
    """
    try:
        req = urllib.request.Request(
            GITHUB_INSTALLER_API_RELEASES,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": "HadesAccessibilityInstaller"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            releases = json.loads(resp.read().decode("utf-8"))

        for release in releases:
            tag = release.get("tag_name", "")
            # Only look at installer-tagged releases (e.g. "installer-1.2")
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
        self.latest_release = None  # (tag, assets, body) from get_latest_mod_release

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
        main_sizer.Add(btn_sizer, 0, wx.LEFT | wx.TOP, 10)

        # License buttons
        license_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.license_btn = wx.Button(panel, label="View License")
        license_sizer.Add(self.license_btn, 0)
        self.original_license_btn = wx.Button(panel, label="View Original License")
        license_sizer.Add(self.original_license_btn, 0, wx.LEFT, 5)
        main_sizer.Add(license_sizer, 0, wx.LEFT | wx.TOP | wx.BOTTOM, 10)

        # Log area (read-only)
        self.log_text = wx.TextCtrl(panel, style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP, size=(500, 250))
        main_sizer.Add(self.log_text, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        panel.SetSizer(main_sizer)
        main_sizer.Fit(self)

        # Bind events
        self.browse_btn.Bind(wx.EVT_BUTTON, self.on_browse)
        self.install_btn.Bind(wx.EVT_BUTTON, self.on_install)
        self.log_btn.Bind(wx.EVT_BUTTON, self.on_open_debug_log_folder)
        self.license_btn.Bind(wx.EVT_BUTTON, self.on_view_license)
        self.original_license_btn.Bind(wx.EVT_BUTTON, self.on_view_original_license)
        self.exit_btn.Bind(wx.EVT_BUTTON, self.on_exit)

        self.Centre()

        # Check for mod updates after frame is shown
        wx.CallAfter(self._start_mod_update_check)

    def _start_mod_update_check(self):
        """Start checking for mod updates in a background thread."""
        thread = threading.Thread(target=self._mod_update_check_thread, daemon=True)
        thread.start()

    def _mod_update_check_thread(self):
        """Background thread: fetch latest release and check for updates."""
        tag, assets, body = get_latest_mod_release()
        if tag and assets:
            self.latest_release = (tag, assets, body)
        wx.CallAfter(self._show_mod_update_if_available, tag, body)

    def _show_mod_update_if_available(self, tag, body):
        """Show mod update dialog if a newer version is available."""
        if not self.game_dir or not tag:
            return

        x64_dir = os.path.join(self.game_dir, "x64")
        installed_version = get_installed_mod_version(x64_dir)
        if not installed_version:
            return  # First install, no update check needed

        if not _mod_version_newer(tag, installed_version):
            return  # Already up to date

        msg = f"A new mod version is available: {tag}\nYou currently have: {installed_version}\n"
        if body:
            msg += f"\nChanges:\n{body}"
        msg += "\n\nWould you like to install the update?"

        nvda_speak(f"New mod version available: {tag}. You have {installed_version}.")
        result = wx.MessageBox(msg, "Mod Update Available", wx.YES_NO | wx.ICON_INFORMATION, self)
        if result == wx.YES:
            self.on_install(None)

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
        """Download files from GitHub release and install."""
        errors = []
        copied = 0
        installer_dir = get_installer_dir()
        installed_tag = None

        # Get release info (use cached if available from update check)
        tag, assets, body = None, None, None
        if self.latest_release:
            tag, assets, body = self.latest_release
        else:
            self.log("Fetching latest release...")
            tag, assets, body = get_latest_mod_release()

        if tag:
            self.log(f"Installing mod version {tag}...")
            installed_tag = tag
        else:
            self.log("Warning: Could not find latest release. Downloading from main branch...")

        try:
            # Check if release has a zip file (new workflow)
            zip_url = assets.get("_zip_url") if assets else None

            if zip_url:
                # Download and extract from zip
                self.log("Downloading mod package...")
                tmp_zip = None
                try:
                    tmp_fd, tmp_zip = tempfile.mkstemp(suffix=".zip")
                    os.close(tmp_fd)
                    urllib.request.urlretrieve(zip_url, tmp_zip)
                    self.log("  Download complete. Extracting files...")

                    with zipfile.ZipFile(tmp_zip, "r") as zf:
                        # Find files inside the zip (may be in a subfolder)
                        zip_contents = zf.namelist()

                        # Extract DLL files to x64 directory
                        for filename in INSTALL_FILES:
                            # Find the file in the zip (could be at root or in a subfolder)
                            zip_path = self._find_in_zip(zip_contents, filename)
                            if zip_path:
                                try:
                                    dest = os.path.join(x64_dir, filename)
                                    with zf.open(zip_path) as src, open(dest, "wb") as dst:
                                        dst.write(src.read())
                                    copied += 1
                                    self.log(f"  {filename} installed.")
                                except PermissionError:
                                    msg = f"Permission denied writing {filename}. Is Hades running? Close the game and try again."
                                    errors.append(msg)
                                    self.log(f"  Error: {msg}")
                                except Exception as e:
                                    msg = f"Error installing {filename}: {e}"
                                    errors.append(msg)
                                    self.log(f"  Error: {msg}")
                            else:
                                msg = f"{filename} not found in zip."
                                errors.append(msg)
                                self.log(f"  Warning: {msg}")

                        # Save readme to installer folder if checked
                        if self.readme_cb.GetValue():
                            zip_path = self._find_in_zip(zip_contents, README_FILE)
                            if zip_path:
                                try:
                                    dest = os.path.join(installer_dir, README_FILE)
                                    with zf.open(zip_path) as src, open(dest, "wb") as dst:
                                        dst.write(src.read())
                                    self.log(f"  Readme saved to {installer_dir}")
                                except Exception as e:
                                    self.log(f"  Error saving readme: {e}")

                        # Save changelog to installer folder if checked
                        if self.changelog_cb.GetValue():
                            zip_path = self._find_in_zip(zip_contents, CHANGELOG_FILE)
                            if zip_path:
                                try:
                                    dest = os.path.join(installer_dir, CHANGELOG_FILE)
                                    with zf.open(zip_path) as src, open(dest, "wb") as dst:
                                        dst.write(src.read())
                                    self.log(f"  Changelog saved to {installer_dir}")
                                except Exception as e:
                                    self.log(f"  Error saving changelog: {e}")

                except urllib.error.URLError as e:
                    msg = f"Failed to download mod package: {e}"
                    errors.append(msg)
                    self.log(f"  Error: {msg}")
                except zipfile.BadZipFile:
                    msg = "Downloaded file is not a valid zip archive."
                    errors.append(msg)
                    self.log(f"  Error: {msg}")
                except Exception as e:
                    msg = f"Error extracting mod package: {e}"
                    errors.append(msg)
                    self.log(f"  Error: {msg}")
                finally:
                    if tmp_zip and os.path.isfile(tmp_zip):
                        try:
                            os.remove(tmp_zip)
                        except Exception:
                            pass
            else:
                # Fallback: download individual files (old workflow or main branch)
                for filename in INSTALL_FILES:
                    try:
                        self.log(f"Downloading {filename}...")
                        dest = os.path.join(x64_dir, filename)
                        if assets and filename in assets:
                            download_url = assets[filename]
                        else:
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
                        if assets and README_FILE in assets:
                            download_url = assets[README_FILE]
                        else:
                            download_url = GITHUB_RAW_BASE + README_FILE
                        urllib.request.urlretrieve(download_url, dest)
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
                        if assets and CHANGELOG_FILE in assets:
                            download_url = assets[CHANGELOG_FILE]
                        else:
                            download_url = GITHUB_RAW_BASE + CHANGELOG_FILE
                        urllib.request.urlretrieve(download_url, dest)
                        self.log(f"  Changelog saved to {installer_dir}")
                    except Exception as e:
                        msg = f"Failed to save changelog: {e}"
                        errors.append(msg)
                        self.log(f"  Error: {msg}")

        except Exception as e:
            errors.append(f"Unexpected error: {e}")

        # Clean up old mod files (Content/Mods/, modimporter.py, mod.log)
        game_dir = os.path.dirname(x64_dir)
        self.log("Checking for old mod files...")
        removed = remove_old_mod_files(game_dir, self.log)
        if removed:
            self.log(f"  Removed legacy files: {', '.join(removed)}")
            self.log("  (All mods are now embedded in the DLL — external mod files are no longer needed.)")
        else:
            self.log("  No old mod files found.")

        # Update UI on main thread
        def finish():
            self.install_btn.Enable()
            if errors:
                self.log(f"\nInstallation completed with errors. {copied}/{len(INSTALL_FILES)} files installed.")
            else:
                self.log(f"\nInstallation complete! {copied} files installed to {x64_dir}")
                self.installed = True
                self.log_btn.Enable()
                if installed_tag:
                    save_installed_mod_version(x64_dir, installed_tag)
                    self.log(f"Installed version: {installed_tag}")

        wx.CallAfter(finish)

    @staticmethod
    def _find_in_zip(zip_contents, filename):
        """Find a file in a zip archive, checking both root and subfolders."""
        filename_lower = filename.lower()
        for entry in zip_contents:
            # Match exact filename at any folder depth
            basename = entry.rsplit("/", 1)[-1] if "/" in entry else entry
            if basename.lower() == filename_lower:
                return entry
        return None

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

    def on_view_license(self, event):
        webbrowser.open(GITHUB_LICENSE_URL)

    def on_view_original_license(self, event):
        webbrowser.open(GITHUB_ORIGINAL_LICENSE_URL)

    def on_exit(self, event):
        self.Close()


def download_update(download_url, new_version):
    """Download new installer next to the current one.
    Downloads to a temp name, then schedule_self_replace will swap them.
    Returns the path to the downloaded file, or None on failure.
    """
    installer_dir = get_installer_dir()
    # Download to a temp name — the batch script will rename it after the old exe exits
    new_exe_path = os.path.join(installer_dir, "_HadesAccessibilityInstaller_update.exe")

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


def schedule_self_replace(new_exe_path):
    """Schedule replacement of the current exe after the process exits.
    Deletes the old exe, renames the new one to HadesAccessibilityInstaller.exe,
    then cleans up the batch script.
    """
    if not getattr(sys, 'frozen', False):
        return
    import subprocess
    current_exe = sys.executable
    installer_dir = os.path.dirname(current_exe)
    final_name = os.path.join(installer_dir, "HadesAccessibilityInstaller.exe")
    bat_path = os.path.join(installer_dir, "_cleanup.bat")
    try:
        with open(bat_path, "w") as bat:
            bat.write("@echo off\n")
            bat.write("timeout /t 2 /nobreak >nul\n")
            bat.write(f'del /f "{current_exe}"\n')
            bat.write(f'move /y "{new_exe_path}" "{final_name}"\n')
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
                    f"This installer will now close and be replaced with the new version.",
                    "Update Downloaded",
                    wx.OK | wx.ICON_INFORMATION
                )
                schedule_self_replace(new_path)
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
