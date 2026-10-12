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
    if not source.exists():
        raise FileNotFoundError(f'missing declared showcase source: {source}')
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
provenance.append({
    'scene':'tiling',
    'composition':'Two separate exact-candidate qualification captures placed side by side in HTML',
    'captures':['showcase/assets/pcmanfm-qualification.png','showcase/assets/foot-fish-current.png'],
})
provenance.append({
    'artifact':{'id':11759890454,'sha256':'e4ce8011a861b87de1bbfadfd499c27a08257c8eeef9be43c3a188e7c19c1152'},
    'source':'native-live/gui-02-file-manager-F4-mapped.png',
    'transformation':'crop x=0 y=0 width=1280 height=720',
    'output':'showcase/assets/pcmanfm-qualification.png',
    'output_sha256':'a5ff22f9a5518f53afff0e96ec00138ac5200823a38f1bddb5e904c9f4d471a7',
})
provenance.append({
    'artifact':{'id':11761152978,'sha256':'8c1a2d34f0b620dec53c6e5efa19f41c2ab9336e3925648540f7b129519c4c4c'},
    'sources':[
        {'path':'vm/boot-52-terminal.png','sha256':'1f79c06d45f6e2df6f1c2b628c23bbdbc3cebd924936f992bdc560f145ad8f00','output':'showcase/assets/foot-fish-current.png'},
        {'path':'vm/boot-51-desktop.png','sha256':'40d7a378b8f727dfff4ae4b7234958329f37f59ed9462417260a3031b8035272','transformation':'JPEG quality 92, 4:4:4, no crop','output':'showcase/assets/installed-desktop-exact.jpg','output_sha256':'9ec51efc605a5a8d144319702dedc9b34d263195ce1b9ce10f3db48c768e65a7'},
    ],
})
provenance.append({
    'artifact':{'id':11762348140,'sha256':'26c5d39f914d6d7ae9dcfab558fc37dd593a9d901896e4f8f854b48e535e0126'},
    'sources':[
        {'path':'dictation-indicator-online-installed.png','sha256':'341b144e1f1ee92c0e365de39463946dcddf279db1105c0615680bc3a6a3b853','output':'showcase/assets/dictation-recording-current.png'},
        {'path':'dictation-indicator-recovered-offline.png','sha256':'252c27ecc4c417311ab49913aa060b54034b7fe548eae83f4f3f2ad12274a230','output':'showcase/assets/dictation-recovery-qualification.png'},
    ],
})
provenance.append({'continuous_os_recording':False,'qualification_capture_disclosures_retained':True})
(ROOT/'asset-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
print(f'Prepared {len(provenance)} authentic screen assets')
