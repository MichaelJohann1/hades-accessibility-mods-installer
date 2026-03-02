# Hades Accessibility Mods Installer

Installs the [Hades Accessibility Mods](https://github.com/MichaelJohann1/hades-accessibility-mods) to your game directory. It finds your Hades install automatically through Steam, downloads the mod files, and copies them to the right place. Checks for installer updates on startup.

[Download the latest installer](https://github.com/MichaelJohann1/hades-accessibility-mods-installer/releases/latest/download/HadesAccessibilityInstaller.exe)

## Building from source

Python 3.12+ required.

```
pip install wxPython pyinstaller
pyinstaller --clean HadesAccessibilityInstaller.spec
```

Output goes to `dist/`.
