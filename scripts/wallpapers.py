#!/home/bitzonx/.local/opt/quickshell-wallpaper-venv/bin/python
import fcntl, hashlib, json, os, subprocess, sys, time
from urllib.parse import unquote, urlparse
from pathlib import Path
from PIL import Image, ImageOps
HOME = Path.home()
CACHE = HOME / '.cache/quickshell-wallpapers'
CACHE.mkdir(parents=True, exist_ok=True)
CONFIG = HOME / '.config/quickshell/wallpapers.json'

def settings():
    return json.loads(CONFIG.read_text())

def save(data):
    temp = CONFIG.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2)+'\n')
    temp.replace(CONFIG)

def ensure_daemon():
    if subprocess.run([str(HOME/'.local/bin/awww'), 'query'], capture_output=True).returncode == 0:
        return
    with (CACHE/'daemon.log').open('a') as log:
        subprocess.Popen([str(HOME/'.local/bin/awww-daemon')], stdout=log, stderr=log, start_new_session=True)
    for _ in range(40):
        time.sleep(0.1)
        if subprocess.run([str(HOME/'.local/bin/awww'), 'query'], capture_output=True).returncode == 0:
            return
    raise RuntimeError('Wallpaper service could not start.')

def run(args):
    result = subprocess.run([str(x) for x in args], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[-500:])
    return result.stdout

def rgb(value):
    return tuple(int(value[i:i+2], 16)/255 for i in (1,3,5))

def hexcolor(values):
    return '#' + ''.join(f'{round(v*255):02x}' for v in values)

def mix(a, b, amount):
    return tuple(x*(1-amount)+y*amount for x,y in zip(a,b))

def luminance(values):
    linear = [v/12.92 if v <= 0.04045 else ((v+0.055)/1.055)**2.4 for v in values]
    return sum(v*w for v,w in zip(linear, (0.2126,0.7152,0.0722)))

def theme(path):
    with (CACHE/'theme.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        run([HOME/'.local/opt/quickshell-wallpaper-venv/bin/wal', '-i', path, '--backend', 'colorthief', '-n', '-s', '-t', '-e', '-q'])
        palette = json.loads((HOME/'.cache/wal/colors.json').read_text())
        # Preserve the wallpaper hue while ensuring readable UI controls.
        bg = mix(rgb(palette['special']['background']), (0.08,0.08,0.09), 0.5)
        accent = rgb(palette['colors']['color4'])
        while luminance(accent) < 0.4:
            accent = mix(accent, (1,1,1), 0.08)
        palette['ui'] = dict(background=hexcolor(bg), surface=hexcolor(mix(bg,(1,1,1),0.07)), accent=hexcolor(accent))
        target = CACHE/'theme.json'
        temp = CACHE/'theme.tmp'
        temp.write_text(json.dumps(palette))
        temp.replace(target)

def library():
    c = settings()
    folder = Path(c.get('folder', '~/Pictures/wallpaper')).expanduser()
    rows = []
    for path in sorted(folder.rglob('*')):
        if path.suffix.lower() not in {'.jpg','.jpeg','.png','.webp','.bmp','.gif'} or not path.is_file():
            continue
        try:
            key = hashlib.sha256((str(path)+str(path.stat().st_mtime_ns)).encode()).hexdigest()
            thumb = CACHE/(key+'.jpg')
            with Image.open(path) as img:
                width, height = img.size
                if not thumb.exists():
                    ImageOps.fit(img.convert('RGB'), (480,300)).save(thumb, quality=85)
            rows.append(dict(path=str(path), name=path.stem.replace('-',' ').replace('_',' '), url=path.as_uri(), thumb=thumb.as_uri(), dimensions=f'{width} × {height}'))
        except (OSError, ValueError):
            continue
    return dict(items=rows, current=str(Path(c.get('wallpaper','')).expanduser()), folder=str(folder))

try:
    action = sys.argv[1]
    if action == 'list':
        print(json.dumps(library()))
    elif action == 'folder':
        path = Path(unquote(urlparse(sys.argv[2]).path) if sys.argv[2].startswith('file:') else sys.argv[2]).expanduser().resolve()
        if not path.is_dir():
            raise ValueError('Choose an existing folder.')
        data = settings(); data['folder'] = str(path); save(data)
        print(json.dumps(dict(ok=True)))
    elif action in ('apply','theme','restore'):
        path = Path(settings()['wallpaper'] if action == 'restore' else sys.argv[2]).expanduser().resolve()
        if not path.is_file():
            raise ValueError('Wallpaper file is missing.')
        if action in ('apply', 'restore'):
            ensure_daemon()
            run([HOME/'.local/bin/awww','img',path,'--transition-type','fade','--transition-duration','0.6'])
            query = run([HOME/'.local/bin/awww', 'query'])
            if str(path) not in query:
                raise RuntimeError('The wallpaper service did not confirm the selected image.')
            data = settings(); data['wallpaper'] = str(path); save(data)
        try:
            theme(path)
        except Exception as error:
            if action == 'apply':
                print(json.dumps(dict(ok=False, applied=True, error='Wallpaper applied, but colors could not update: '+str(error))))
                sys.exit(0)
            raise
        print(json.dumps(dict(ok=True, applied=action=='apply', path=str(path))))
except Exception as error:
    print(json.dumps(dict(ok=False, error=str(error))))
    sys.exit(1)
