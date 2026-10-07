#!/usr/bin/env python3
"""Reproduce the private helper; preserve upstream emitted-input functions verbatim."""
import argparse,hashlib,json
from pathlib import Path
BASE_SHA='713597abfc049196864ffcc041bb6683c761b71d68ed2da86cdcfc6b7ed3d244'
def generate(base):
 if hashlib.sha256(base).hexdigest()!=BASE_SHA:raise ValueError('Exact original wtype0.4 source required')
 text=base.decode()
 pairs=[
 ('#include "virtual-keyboard-unstable-v1-client-protocol.h"', '#include "virtual-keyboard-unstable-v1-client-protocol.h"\n#include "arctic-proof.h"'),
 ('\tfprintf(f, "};\\n");\n\n\t// TODO: Is including "complete"', '\tfprintf(f, "<ARCTIC_UNUSED> = %ld;\\n", wtype->keymap_len + 9);\n\tfprintf(f, "};\\n");\n\n\t// TODO: Is including "complete"'),
 ('\tsize_t keymap_size = ftell(f);\n\n\tzwp_virtual_keyboard_v1_keymap(', '\tsize_t keymap_size = ftell(f);\n\tarctic_record_map(f, keymap_size, wtype->keymap_len);\n\tif (arctic_map_only) { fclose(f); exit(EXIT_SUCCESS); }\n\n\tzwp_virtual_keyboard_v1_keymap('),
 ('\tparse_args(&wtype, argc, argv);', '\tarctic_initialize(argc, argv);\n\targc -= 3;\n\targv += 3; /* argv[0] is the explicit -- boundary; original parser starts at1. */\n\tparse_args(&wtype, argc, argv);\n\tif (arctic_map_only) { upload_keymap(&wtype); return EXIT_SUCCESS; }')
 ]
 for before,after in pairs:
  if text.count(before)!=1:raise ValueError('Upstream insertion boundary differs')
  text=text.replace(before,after,1)
 return text.encode()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 root=Path(__file__).resolve().parent
 if a.out.exists():raise RuntimeError('Unused helper output required')
 a.out.write_bytes(generate((root/'original-wtype-v0.4.c').read_bytes()))
 print(json.dumps(dict(source=a.out.name,bytes=a.out.stat().st_size,sha256=hashlib.sha256(a.out.read_bytes()).hexdigest())))

