# Arctic Linux showcase

The video below is the published **3 October 2026** edition. A replacement English walkthrough
with ElevenLabs River narration and the current default apps and photo wallpapers is being
prepared. Its locked script now covers Arctic's direct integration of official VoxType 1.1.1:
verified automatic online setup, a clear offline first-boot retry, local Hebrew and English
Whisper, Mango shortcuts and Arctic's VoxType-backed indicator. The source reports the hosted Westmere
CPU measurements honestly: 7.77% English word error, 42.0% Hebrew word error, and slower-than-real-
time processing. Those are the earlier measurements spoken by the locked River master. The later
exact-image VoxType 1.1.1 fixture measured Small v2 at 7.77% English and 41.0% Hebrew WER, and
Turbo Q5 v3 at 6.80% and 21.0%, respectively. Both are small virtual-source public read-speech
fixtures; neither claims general parity, physical-microphone coverage or real-time CPU performance.

The old custom-controller screenshots and their River audio are superseded. Five explicit
capture contracts now require evidence from the qualified ISO: three for direct VoxType, one for
packaged-wallpaper hide and restore, and one for the per-update What's New summary. The retained
artifact-only candidate from [run 38808271154](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/38808271154)
is 1,936,328,704 bytes with SHA-256
`304ae134793773f7a4d58ebe4dc4a5428a49754f474749d0d0a025032da70b23`, but no capture is admitted
until its exact-image receipt and pixels pass the automated contract and human review. A new River
master has deterministic local alignment and still needs human listening. The locked narration is 9,093 characters, above
the connected generator's 5,000-character request limit. The failed full-script attempt has no
renderable audio. Two exact source segments of 4,451 and 4,642 characters are pinned at a paragraph
boundary. Both one-take River generations completed and their receipts were verified. The
sample-exact assembled master uses River voice ID `SAz9YHcvj6GT2YYXdXww` with
`eleven_multilingual_v2`. It is 13,978,270 bytes and 582.356463 seconds, with SHA-256
`f6852132fed3f97e3b6a6b69fe4543e6af1a26c8495c9243e2cccfbde7c7081b`; it remains unpublished.
Two offline faster-whisper 1.2.1 runs produced byte-identical timing for all 130 cues, with 4.1412%
WER and 97.4202% exact-token coverage. A full decode found no errors or hard-clipped samples; its
measured loudness is -24.6 LUFS with a -2.2 dBTP true peak, and the segment boundary lies inside
0.431905 seconds below -60 dBFS. These automated results do not replace
listening. The exact master is preserved in a verified private draft release. A private render is
blocked pending qualified captures and release binding; publication additionally requires complete
human listening, final video and frame review, confirmation that the connected ElevenLabs plan
permits the public video, and verified public downloads. No replacement video link is published yet.

[![Watch the Arctic Linux showcase](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/download/showcase-2026-10-03/Arctic-Linux-Showcase-Poster.png)](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/download/showcase-2026-10-03/Arctic-Linux-Showcase-1080p.mp4)

**[Watch or download the full video](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/download/showcase-2026-10-03/Arctic-Linux-Showcase-1080p.mp4)** · [Release and editable source](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/tag/showcase-2026-10-03) · [English captions (SRT)](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/download/showcase-2026-10-03/captions.srt) · [Web captions (VTT)](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/download/showcase-2026-10-03/captions.vtt)

A narrated, **6 minute 47 second** tour in **1080p at 30 fps**, covering the live USB, every installer step, and everyday desktop use. The daily-use scenes show **Nautilus (GNOME Files)** and **Kitty with Fish**.

## Chapters

```text
00:00 Meet Arctic Linux
00:12 01 · From USB to your desktop
00:34 02 · The installer
02:45 03 · A day on Arctic
04:30 04 · Make it yours
05:07 05 · The everyday details
06:03 06 · Keep it running
06:31 Arctic Linux
```

The tour includes the launcher and calculator, tiling and workspaces, files, terminal, getting apps, Settings, themes and wallpaper, Quick settings, Wi-Fi, displays, shortcuts, updates, and screen locking. English captions are shown in the video and included as a selectable subtitle track.

## About the recording

This HyperFrames video animates repository screenshots and real application captures. Installer screens use demo data. Nautilus and Kitty/Fish were captured on Fedora 44 with Arctic’s styles; the tiled scene combines separate app captures over the Arctic desktop. It is a visual walkthrough, rather than a continuous recording of an installation. Some documented preview screens show choices from an earlier build.

The natural-speed narration uses Kokoro’s `af_heart` voice. The [source project](https://github.com/yuvalkolodkingal/Arctic-Linux/tree/main/showcase) includes the storyboard, narration, timing, caption files, assets, provenance, and render instructions.
