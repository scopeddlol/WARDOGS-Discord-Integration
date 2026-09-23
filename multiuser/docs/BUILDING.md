# Build and verification

All commands below start in `multiuser/`. This edition deliberately has its own dependencies, packaging, tests and source snapshot. It imports no application modules from the repository root. Root standalone behavior and release workflow remain unchanged.

## Controller development

Use Python 3.12:

```sh
python -m venv .venv
# Activate the environment for your shell.
python -m pip install -r controller/requirements.txt pytest==8.4.2
python -m pytest checks/controller_checks.py -q
```

Set `CONTROLLER_DATA_DIR` to a disposable directory, `CONTROLLER_ADMIN_TOKEN` to a test secret of at least 32 characters, and `DISCORD_DRY_RUN=1`, then run:

```sh
python -m uvicorn controller.app:create_app --factory --host 127.0.0.1 --port 8765
```

Visit `http://127.0.0.1:8765/`. Dry-run mode never contacts Discord. Test transport uses synthetic player reports; preview samples never enter the live roster. `checks/container_smoke.py --url http://127.0.0.1:18080 --token YOUR_TEST_SECRET` exercises ten agents, uploads an image and saves a layout against a disposable running controller.

## Windows build

Install Python 3.12 x64, Inno Setup 6 and 7-Zip. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.\.venv\Scripts\python.exe -m pytest checks/agent_checks.py -q
.\packaging\prepare-ocr.ps1
.\packaging\build.ps1
.\packaging\test-installer.ps1
```

`build.ps1` accepts `-Python` and `-ISCC` overrides. OCR preparation downloads the pinned upstream Tesseract installer and checks its SHA-256 before extraction. Packaging bundles its required DLLs, English/orientation data and third-party notices. No runtime download is needed by players.

Output: `dist/WARDOGS-Agent-Setup.exe` and `dist/SHA256SUMS.txt`. The installer test installs to a unique directory under `artifacts`, launches the installed GUI in offscreen smoke mode, performs actual OCR on a generated image, upgrades in place while checking data preservation, then uninstalls. It uses an isolated settings directory and does not contact Discord or the controller. Run it as the same normal Windows user that builds/tests DPAPI credentials.

## Automation and coverage

`.github/workflows/multiuser.yml` runs controller behavior tests on Linux, builds the actual non-root Docker image, exercises ten agents over HTTP and verifies database/image-layout persistence after restart. Its Windows job checks agent privacy, transport, DPAPI and interface behavior, then builds and lifecycle-tests the installer. Download the `multiuser-agent-installer` artifact from that run; verification evidence is a separate artifact.

Test files use `*_checks.py` and are invoked explicitly so the standalone project's existing pytest discovery is unaffected. Controller checks use a mock Discord transport to verify one create followed by edits, deleted-message recovery, attachment retention/removal and rate-limit handling. Tests do not require or leak a real bot token.

Actual WARDOGS gameplay and a real Discord channel remain environment-dependent acceptance checks. Test those after configuring your own controller. Browser previews approximate Discord rendering; Discord is the final authority on Markdown, layout and media handling.

The isolated `agent/engine.py` and calibration code originate from the root project's OCR implementation at commit `448eb24`. Future OCR fixes should be evaluated and copied deliberately; neither edition should import the other's runtime configuration or credentials.
