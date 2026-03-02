# Hades Accessibility Mods Installer

A Windows installer for the [Hades Accessibility Mods](https://github.com/MichaelJohann1/hades-accessibility-mods).

## Download

Download the latest installer from [Releases](https://github.com/MichaelJohann1/hades-accessibility-mods-installer/releases/latest/download/HadesAccessibilityInstaller.exe).

## Features

- Automatically detects your Hades game directory via Steam
- Downloads and installs the latest accessibility mod DLL files
- Optional readme and changelog saving to the installer's folder
- Copy Debug Log button for sharing the accessibility log
- NVDA screen reader support for all installer messages
- Automatic update checking on startup

## Requirements

- Windows
- NVDA screen reader

## Building from Source

Requires Python 3.12+ with wxPython and PyInstaller:

```
pip install wxPython pyinstaller
pyinstaller --clean HadesAccessibilityInstaller.spec
```

The built installer will be in the `dist/` folder.
