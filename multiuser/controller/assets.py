"""Private uploaded raster assets, attached directly to the Discord message."""
import hashlib
from io import BytesIO
from pathlib import Path
import re
import warnings
from PIL import Image

MAX_BYTES = 8 * 1024 * 1024
MIMES = {'png': 'image/png', 'jpg': 'image/jpeg', 'gif': 'image/gif', 'webp': 'image/webp'}


class Assets:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def file(self, name):
        if not re.fullmatch(r'[a-f0-9]{64}\.(png|jpg|gif|webp)', name):
            raise ValueError('Invalid uploaded image reference.')
        path = self.path / name
        if not path.is_file():
            raise ValueError('An uploaded image no longer exists. Upload it again.')
        return path

    def add(self, data):
        if not data or len(data) > MAX_BYTES:
            raise ValueError('Choose an image up to 8 MB.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(data)) as image:
                    suffix = {'PNG': 'png', 'JPEG': 'jpg', 'GIF': 'gif', 'WEBP': 'webp'}.get(image.format)
                    if not suffix or image.width * image.height > 16_777_216:
                        raise ValueError('Use PNG, JPEG, GIF or WebP, at most 16 megapixels.')
                    image.verify()
        except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
            raise ValueError('This file is not a supported, valid raster image.') from error
        name = hashlib.sha256(data).hexdigest() + '.' + suffix
        target = self.path / name
        if not target.exists():
            if sum(p.stat().st_size for p in self.path.iterdir() if p.is_file()) + len(data) > 256 * 1024 * 1024:
                raise ValueError('The image store is full (256 MB). Remove unused assets from the data volume.')
            # Unique content-addressed filenames; concurrent identical uploads have identical bytes.
            target.write_bytes(data)
        return {'reference': 'attachment://' + name, 'name': name, 'bytes': len(data)}

    def read(self, name):
        return self.file(name).read_bytes(), MIMES[name.rsplit('.', 1)[1]]
