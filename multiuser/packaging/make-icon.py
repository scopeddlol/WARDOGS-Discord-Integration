"""Generate the neutral WARDOGS agent mark for the tray and installer."""
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
size = 512
im = Image.new('RGBA', (size, size), (0, 0, 0, 0))
d = ImageDraw.Draw(im)
d.rounded_rectangle((20, 20, 492, 492), radius=108, fill='#111c28', outline='#385269', width=8)
d.ellipse((78, 78, 434, 434), outline='#356174', width=10)
d.arc((108, 108, 404, 404), 215, 325, fill='#6adad3', width=19)
d.arc((124, 124, 388, 388), 35, 145, fill='#6adad3', width=19)
d.line([(119, 188), (174, 345), (236, 244), (286, 345), (393, 177)], fill='#e8f6f1', width=32, joint='curve')
d.ellipse((374, 158, 405, 189), fill='#c8e47a')
im.save(root / 'agent' / 'tray_icon.png')
im.save(root / 'packaging' / 'app.ico', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
