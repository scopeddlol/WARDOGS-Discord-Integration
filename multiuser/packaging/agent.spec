from pathlib import Path
import pefile

root = Path(SPECPATH).parent
ocr = root / 'vendor' / 'tesseract'
if not (ocr / 'tesseract.exe').exists() or not (ocr / 'tessdata' / 'eng.traineddata').exists():
    raise RuntimeError('Run packaging/prepare-ocr.ps1 first.')
# Keep the OCR runtime external to Qt/Python DLL search paths. Include upstream notices.
datas = [(str(root / 'agent' / 'tray_icon.png'), 'agent'), (str(root / 'LICENSE'), 'licenses'),
         (str(root / 'docs' / 'THIRD_PARTY.md'), 'licenses'),
         (str(root / 'vendor' / 'licenses'), 'licenses/dependencies')]
# Include only the engine's dependency closure, not training tools and their DLLs.
needed = set()
def include_ocr(name):
    path = ocr / name
    if name.lower() in needed or not path.is_file():
        return  # Windows system DLLs are supplied by the OS.
    needed.add(name.lower())
    datas.append((str(path), 'tesseract'))
    binary = pefile.PE(str(path), fast_load=True)
    binary.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    for entry in getattr(binary, 'DIRECTORY_ENTRY_IMPORT', []):
        include_ocr(entry.dll.decode())
    binary.close()
include_ocr('tesseract.exe')
datas += [(str(ocr / 'tessdata' / name), 'tesseract/tessdata') for name in ('eng.traineddata', 'osd.traineddata')]
datas += [(str(ocr / 'doc'), 'tesseract/doc')]
a = Analysis([str(root / 'run_agent.py')], pathex=[str(root)], datas=datas,
             hiddenimports=[], excludes=['tkinter', 'PySide6.QtQml', 'PySide6.QtQuick'], noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='WARDOGS Agent',
          console=False, icon=str(root / 'packaging' / 'app.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='WARDOGS Agent')
