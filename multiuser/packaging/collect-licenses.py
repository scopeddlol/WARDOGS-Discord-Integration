"""Collect notices from the exact installed dependencies being redistributed."""
from importlib.metadata import distributions
from pathlib import Path
import shutil
import sys
from PIL import Image

root = Path(__file__).resolve().parent.parent
out = root / 'vendor' / 'licenses'
out.mkdir(parents=True, exist_ok=True)
python_license = Path(sys.base_prefix) / 'LICENSE.txt'
if python_license.exists():
    shutil.copy2(python_license, out / 'Python-LICENSE.txt')
shutil.copytree(root / 'licenses', out / 'upstream', dirs_exist_ok=True)
for package in distributions():
    name = package.metadata['Name']
    destination = out / name
    destination.mkdir(exist_ok=True)
    (destination / 'METADATA.txt').write_text(package.read_text('METADATA') or package.read_text('PKG-INFO') or name, encoding='utf-8')
    for file in package.files or []:
        if any(marker in str(file).lower() for marker in ('license', 'copying', 'notice', 'copyright')):
            source = Path(package.locate_file(file))
            if source.is_file():
                target = destination / str(file).replace('..', '_').replace('/', '_').replace('\\', '_')
                shutil.copy2(source, target)
Image.open(root / 'agent' / 'tray_icon.png').save(root / 'packaging' / 'app.ico', sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
