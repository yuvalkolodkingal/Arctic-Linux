import http.server, os, socket, struct, sys, time, zlib
LOG = sys.argv[2]
def png(size, rgb):
    raw = b"".join(b"\0" + bytes(rgb) * size for _ in range(size))
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
ICON = png(96, (40, 110, 200))
PAGES = {
    "/": b"<!doctype html><html><head><title>Smoke Home</title><link rel=manifest href=/app.webmanifest></head>"
         b"<meta name=color-scheme content='light dark'><style>body{background:#eef2f5;color:#17212b}"
         b"@media(prefers-color-scheme:dark){body{background:#17212b;color:#eef2f5}}</style>"
         b"<body><h1>Smoke</h1><a id=out href='https://example.com/elsewhere'>out</a>"
         b"<a id=in href='/second'>in</a><script>const scheme=matchMedia('(prefers-color-scheme: dark)');"
         b"const report=()=>fetch('/theme-result?dark='+scheme.matches);scheme.addEventListener('change',report);report();"
         b"</script></body></html>",
    "/second": b"<!doctype html><title>Second Page</title><p>second</p>",
    "/app.webmanifest": b'{"name":"Smoke App","start_url":"/","icons":[]}',
    "/notify": b"<!doctype html><title>Notify</title><script>"
               b"new Notification('Smoke').onclose = () => fetch('/notification-closed');</script>",
    "/notification-closed": b"ok",
    "/conversation": b"<!doctype html><title>Conversation</title><script>setTimeout(()=>{let n=new Notification('Conversation 42');n.onclick=()=>{document.title='Opened conversation 42';fetch('/notification-target');};},1500)</script>",
    "/notification-target": b"ok",
    "/paste": b"<!doctype html><title>Paste fixture</title><div contenteditable id=editor>Paste here</div><script>editor.focus();editor.onpaste=e=>{fetch('/paste-result?files='+e.clipboardData.files.length+'&type='+encodeURIComponent(e.clipboardData.files[0]?.type)+'&types='+encodeURIComponent([...e.clipboardData.types].join(',')));setTimeout(()=>fetch('/paste-inserted?images='+editor.querySelectorAll('img').length),500);};</script>",
    "/upload": b"<!doctype html><title>Upload fixture</title><input type=file autofocus multiple onchange=\"fetch('/upload-result?count='+this.files.length+'&name='+encodeURIComponent(this.files[0]?.name))\">",
    "/media": b"<!doctype html><title>Native media fixture</title><audio src='/tone.wav' controls loop></audio><button autofocus onclick=\"document.querySelector('audio').play()\">Play</button>",
    "/capabilities": b"<!doctype html><title>Capabilities</title><script>fetch('/capabilities-result?'+new URLSearchParams({rtc:typeof RTCPeerConnection,media:typeof navigator.mediaDevices?.getUserMedia,screen:typeof navigator.mediaDevices?.getDisplayMedia,session:typeof navigator.mediaSession}));</script>",
    "/rtc": b"<!doctype html><title>WebRTC loopback</title><button autofocus onclick='run()'>Test call transport</button><script>"
            b"async function run(){try{const a=new RTCPeerConnection({iceServers:[]}),b=new RTCPeerConnection({iceServers:[]});"
            b"window.peers=[a,b];a.onicecandidate=e=>{if(e.candidate)b.addIceCandidate(e.candidate)};"
            b"b.onicecandidate=e=>{if(e.candidate)a.addIceCandidate(e.candidate)};"
            b"b.ondatachannel=e=>{e.channel.onmessage=m=>{if(m.data==='arctic-rtc')fetch('/rtc-result?data=ok')}};"
            b"const channel=a.createDataChannel('arctic');channel.onopen=()=>channel.send('arctic-rtc');"
            b"const audio=new AudioContext(),tone=audio.createOscillator(),destination=audio.createMediaStreamDestination();"
            b"tone.connect(destination);tone.start();await audio.resume();window.audio=audio;"
            b"a.addTrack(destination.stream.getAudioTracks()[0],destination.stream);"
            b"const canvas=document.createElement('canvas');canvas.width=320;canvas.height=180;const ctx=canvas.getContext('2d');"
            b"function paint(){ctx.fillStyle='rgb('+Math.floor(performance.now()%255)+',100,150)';ctx.fillRect(0,0,320,180);requestAnimationFrame(paint)}paint();"
            b"const video=canvas.captureStream(15);a.addTrack(video.getVideoTracks()[0],video);"
            b"b.ontrack=e=>{const player=new Audio();player.srcObject=e.streams[0];player.muted=true;player.play();"
            b"const timer=setInterval(async()=>{for(const stat of(await b.getStats()).values()){"
            b"if(stat.type==='inbound-rtp'&&stat.kind===e.track.kind&&stat.bytesReceived>0&&(stat.kind==='audio'||stat.framesDecoded>0)){clearInterval(timer);fetch('/rtc-result?'+stat.kind+'=ok')}}},200)};"
            b"const offer=await a.createOffer();await b.setRemoteDescription(offer);await a.setLocalDescription(offer);"
            b"const answer=await b.createAnswer();await a.setRemoteDescription(answer);await b.setLocalDescription(answer);"
            b"}catch(e){fetch('/rtc-result?error='+encodeURIComponent(e.name+': '+e.message))}}</script>",
}
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        with open(LOG, "a") as f:
            f.write(self.path + "\t" + self.headers.get("User-Agent", "") + "\n")
        if self.path in ("/good.bin", "/broken.bin"):
            # Two downloads: the broken one's connection is reset halfway (a short body alone
            # counts as finished).
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % self.path[1:])
            self.send_header("Content-Length", "10" if self.path == "/good.bin" else "1000000")
            self.end_headers()
            self.wfile.write(b"0123456789")
            if self.path == "/broken.bin":
                time.sleep(1)
                self.connection.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
                self.connection.close()
            return
        body = PAGES.get(self.path.split("?")[0])
        if self.path == "/tone.wav":
            import io, wave
            audio = io.BytesIO()
            with wave.open(audio, 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
                wav.writeframes(b'\0\0' * 80000)
            body = audio.getvalue()
        if self.path.startswith(('/rtc-result?', '/theme-result?', '/capabilities-result?', '/upload-result?', '/paste-result?', '/paste-inserted?')):
            body = b'ok'

        # The favicon appears only after install, so the app starts with a letter icon and the
        # window's favicon upgrade has something to do.
        if self.path == "/favicon.ico" and os.path.exists(LOG + ".icon"):
            body = ICON
        if body is None:
            self.send_error(404)
            return
        self.send_response(200)
        ctype = "text/html; charset=utf-8"
        if self.path.endswith(".wav"):
            ctype = "audio/wav"
        elif self.path.endswith("manifest"):
            ctype = "application/manifest+json"
        elif self.path == "/favicon.ico":
            ctype = "image/png"
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a):
        pass
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
