# Third-party notices

The project is MIT licensed. The Windows installer redistributes independently licensed software:

- Python: PSF license. https://www.python.org/psf/license/
- PySide6 / Shiboken6 / Qt 6.8.3: LGPLv3 / GPLv3 / Qt commercial licensing options.
  This build uses the open-source, dynamically linked distribution. License texts and package
  metadata are included in `_internal/licenses/dependencies`. The DLLs remain replaceable.
  Corresponding Qt source: https://download.qt.io/archive/qt/6.8/6.8.3/single/
  PySide/Shiboken source: https://code.qt.io/cgit/pyside/pyside-setup.git/tag/?h=v6.8.3
  Users may modify/replace these libraries and reverse engineer the application to debug those
  modifications as permitted by the LGPL. No project restriction overrides these rights.
- Tesseract 5.4.0 / English model: Apache-2.0; bundled upstream notices are in
  `_internal/tesseract/doc`. Source: https://github.com/tesseract-ocr/tesseract/tree/5.4.0
  Windows distribution/build recipe: https://github.com/UB-Mannheim/tesseract
  Language data: https://github.com/tesseract-ocr/tessdata
- Tesseract's Windows runtime includes Leptonica and supporting image/compression/runtime DLLs.
  These retain their upstream licenses. See the bundled `upstream` notices and `SOURCES.json`
  for source distribution references, including GPL-licensed JBIG-KIT, LGPL libiconv, and
  the GCC runtime exception. Windows build recipes: https://github.com/msys2/MINGW-packages.
  This software is based in part on the work of the Independent JPEG Group.
- Pillow, mss, psutil, pytesseract, requests, windows-capture, NumPy, OpenCV and their dependencies:
  their installed package metadata and license/notice files accompany the app under
  `_internal/licenses/dependencies`.
- PyInstaller: GPL with a distribution exception for bundled applications.
  https://pyinstaller.org/en/stable/license.html

Build tooling (Inno Setup, 7-Zip, pytest) is not installed as a separate program on users' PCs.
See each upstream project for its build-tool license. This notice does not replace the bundled
license texts. Dependency upgrades must retain relevant licenses and source availability.
