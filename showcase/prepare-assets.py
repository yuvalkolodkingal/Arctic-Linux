"""Copy authentic repository screens and the Arctic brand assets into the video."""
import json
import shutil
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parent
story = json.loads((ROOT/'storyboard.json').read_text())
assets = ROOT/'assets'
assets.mkdir(exist_ok=True)
provenance=[]
for scene in story:
    if 'image' not in scene:
        continue
    source=REPO/scene['source'] if 'source' in scene else REPO/'docs/wiki/images'/(scene['image']+'.png')
    dest=assets/(scene['id']+'.png')
    image=Image.open(source)
    if 'crop' in scene:
        x,y,w,h=scene['crop']
        image=image.crop((x,y,x+w,y+h))
    image.save(dest,optimize=True)
    provenance.append({'scene':scene['id'],'source':str(source.relative_to(REPO)),'crop':scene.get('crop')})
for source in (REPO/'design/fonts').glob('*.woff2'):
    shutil.copy2(source,assets/source.name)
for name in ['arctic-mark-winter.svg','arctic-mark-polar-night.svg']:
    shutil.copy2(REPO/'design/logos'/name,assets/name)
# Bundle GSAP locally so the source can be rendered without a CDN request.
import urllib.request
with urllib.request.urlopen('https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js') as src:
    (assets/'gsap.min.js').write_bytes(src.read())
provenance.append({'scene':'tiling','composition':'Separate real app captures placed over the Arctic desktop in HTML','captures':['showcase/assets/kitty-fish-capture.png','showcase/assets/nautilus-tiled-capture.png']})
provenance.append({'captures':['nautilus-capture.png','nautilus-tiled-capture.png','kitty-fish-capture.png'],'environment':'Fedora 44, headless Sway, real Nautilus 50.3 / Kitty 0.47.1 / Fish 4.6.0','theme':'Repository GTK and Kitty styles; current libadwaita CSS variables set to the Arctic Polar night palette','continuous_os_recording':False})
(ROOT/'asset-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print(f'Prepared {len(provenance)} authentic screen assets')
