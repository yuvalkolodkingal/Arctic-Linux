"""Source/owned-host controls for default-player control-state diagnostics; no VM."""
import ast
import copy
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pwd
import socket
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import zlib

HERE=Path(__file__).resolve().parent
BASE_NATIVE_SHA='e7a0018c02b0d8fb78db3187db5155544e7462841fb5da841eb5cf1c8a80279f'
BASE_GUEST_SHA='29ccacbe04be9306de58f275762a4f0b0dd60220d6ea51e40ad805a8b9485926'
spec=importlib.util.spec_from_file_location('controls_trial_tested',HERE/'native_smoke.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)


BOUNDED_RETRY_NATIVE_SHA = 'e71dd245cb3a3f4a4a722b1f3dc6c42658eaa51475b243de24011ec825078816'
STREAM_NATIVE_SHA = '0171db2b876ad498ef474277325d91e44f5114ebf2f06d44fd9acc2ff92e0a6f'
PRE_STREAM_NATIVE_SHA = '97bb8590869a823171fdd2d84491268527271984a96e88691beb8511c88dc06f'
FRESH_PLAYER_RESTART_NATIVE_SHA = '8caeaa262ca9cdb55de81991c69b16783dae36656b3001870dbb4252ed49118c'
PRE_PRODUCT_LAUNCH_NATIVE_SHA = 'c951fd9d1d5b2efd0f5d8cc8e21dca859dd9f6e908e8b95d03aadc89e9a9223b'
TWO_PLAYER_CURRENT_SHA = '84dd4f74826dc3372f11c96d6399bc763c4eb2ebeb300dbbdbedd601723c396e'


def restore_epiphany_product_route(source):
    """Remove only the fresh-default product-route update for old byte proofs."""
    current = "ROLES = dict(terminal='foot', browser='gtk-launch org.gnome.Epiphany', editor='featherpad', files='pcmanfm')\n"
    previous = "ROLES = dict(terminal='foot', browser='epiphany', editor='featherpad', files='pcmanfm')\n"
    if source.count(current) != 1:
        raise AssertionError('Epiphany product-route inverse occurrence differs')
    return source.replace(current, previous, 1)


def restore_moving_player_retirement(source):
    """Reverse only the sequential moving/static player lifecycle correction."""
    substitutions=(('def rename_noreplace(source_directory,source_name,target_directory,target_name):\n    """Atomically quarantine one directory entry without replacing another."""\n    import ctypes\n    import errno\n    require(all(type(value) is int and value>=0 for value in (source_directory,target_directory))\n            and all(isinstance(name,str) and name and \'/\' not in name and name not in (\'.\',\'..\')\n                    for name in (source_name,target_name)),\n            \'invalid atomic quarantine request\')\n    libc=ctypes.CDLL(None,use_errno=True)\n    operation=libc.renameat2\n    operation.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)\n    operation.restype=ctypes.c_int\n    if operation(source_directory,os.fsencode(source_name),target_directory,\n                 os.fsencode(target_name),1)==0:  # RENAME_NOREPLACE\n        return\n    code=ctypes.get_errno()\n    if code==errno.ENOENT: raise FileNotFoundError(code,os.strerror(code))\n    if code==errno.EEXIST: raise FileExistsError(code,os.strerror(code))\n    raise OSError(code,os.strerror(code))\n\n\n',''),('    def retire_moving_player(self,player,ipc):\n        """Retire the proved moving player before creating the static oracle player."""\n        require(isinstance(ipc,Path) and ipc==self.root/\'celluloid-ipc.sock\'\n                and sum(item is player for item in self.owned)==1,\n                \'moving player retirement target differs\')\n        # A pathname-bound Unix socket normally survives its listener. Pin the\n        # live endpoint before signalling, then atomically quarantine it in a\n        # root-owned directory. The desktop UID cannot replace the quarantined\n        # entry between its held-fd identity check and unlink.\n        fields=(\'st_dev\',\'st_ino\',\'st_mode\',\'st_uid\',\'st_gid\',\'st_nlink\')\n        directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)\n        try:\n            root_info=os.fstat(directory)\n            require(root_info.st_uid==self.uid and stat.S_ISDIR(root_info.st_mode)\n                    and not root_info.st_mode&0o077,\n                    \'moving player IPC directory is not private\')\n            root_identity=(root_info.st_dev,root_info.st_ino)\n            held=os.open(ipc.name,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)\n            try:\n                before=os.fstat(held)\n                require(stat.S_ISSOCK(before.st_mode) and before.st_uid==self.uid and before.st_nlink==1,\n                        \'moving player IPC owner/type differs\')\n                ipc_identity=tuple(getattr(before,key) for key in fields)\n                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:\n                    peer.settimeout(2);peer.connect(str(ipc))\n                    pid,uid,_=struct.unpack(\'3i\',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))\n                    require((pid,uid)==(player[\'pid\'],self.uid),\'moving player IPC peer differs\')\n                after=os.stat(ipc.name,dir_fd=directory,follow_symlinks=False)\n                require(tuple(getattr(after,key) for key in fields)==ipc_identity,\n                        \'moving player IPC identity changed during proof\')\n                retire_renderer_player(player,self.uid)\n                quarantine=Path(tempfile.mkdtemp(prefix=\'.celluloid-ipc-retired-\',dir=self.root))\n                quarantine_info=quarantine.lstat()\n                require(stat.S_ISDIR(quarantine_info.st_mode)\n                        and quarantine_info.st_uid==os.geteuid() and not quarantine_info.st_mode&0o077,\n                        \'moving player IPC quarantine is not private\')\n                quarantine_directory=os.open(quarantine,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)\n                try:\n                    retired_name=\'endpoint.sock\'\n                    try: rename_noreplace(directory,ipc.name,quarantine_directory,retired_name)\n                    except FileNotFoundError: pass\n                    else:\n                        retired=os.open(retired_name,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC,\n                                        dir_fd=quarantine_directory)\n                        try:\n                            retired_info=os.fstat(retired)\n                            if tuple(getattr(retired_info,key) for key in fields)!=ipc_identity:\n                                try: rename_noreplace(quarantine_directory,retired_name,directory,ipc.name)\n                                except (FileNotFoundError,FileExistsError,OSError): pass\n                                raise RuntimeError(\'moving player IPC identity changed before quarantine\')\n                            os.unlink(retired_name,dir_fd=quarantine_directory)\n                        finally: os.close(retired)\n                finally: os.close(quarantine_directory)\n            finally: os.close(held)\n            def fully_retired():\n                path_info=self.root.lstat()\n                require(stat.S_ISDIR(path_info.st_mode) and path_info.st_uid==self.uid\n                        and not path_info.st_mode&0o077\n                        and (path_info.st_dev,path_info.st_ino)==root_identity,\n                        \'moving player IPC directory identity changed after quarantine\')\n                try: os.stat(ipc.name,dir_fd=directory,follow_symlinks=False)\n                except FileNotFoundError: socket_absent=True\n                else:\n                    require(False,\'moving player IPC path was recreated after quarantine\')\n                    socket_absent=False\n                return socket_absent and self.clients().get(player[\'client_id\']) is None\n            self.wait(fully_retired,5,\'moving player process/socket/compositor retirement\')\n            return dict(process_identity_retired=True,owned_ipc_absent=True,\n                        compositor_client_absent=True,release_acceptance=False)\n        finally: os.close(directory)\n\n',''),("""        moving_proof['retirement_before_static_oracle']=None
        (self.root/'moving-player-proof.json').write_text(json.dumps(moving_proof,indent=2))
        if getattr(self,'gui_v6',False):
            self.player_fullscreen(player,False)
            self.finish_native_protocol()
            moving_proof['retirement_before_static_oracle']=self.retire_moving_player(player,ipc)
            (self.root/'moving-player-proof.json').write_text(json.dumps(moving_proof,indent=2))
""","""        (self.root/'moving-player-proof.json').write_text(json.dumps(moving_proof,indent=2))
        if getattr(self,'gui_v6',False):
            self.player_fullscreen(player,False)
            self.finish_native_protocol()
"""),("""                          client=self.alive(player),scope='original moving testsrc2 decode/advancing AV state retained; this frame still requires visual review; proved player is retired before the separate static oracle player')
""","""                          client=self.alive(player),scope='original moving testsrc2 decode/advancing AV state retained; this frame still requires visual review')
"""),("""                    scope='product file-manager/MIME and Gio desktop actions plus enqueue semantics; original moving fixture lossless decode/advancing AV state and sequential separate static rendered-content oracle; motion/perceived audio/hardware remain unqualified')
""","""                    scope='product file-manager/MIME and Gio desktop actions plus enqueue semantics; original moving fixture lossless decode/advancing AV state and separate static rendered-content oracle; motion/perceived audio/hardware remain unqualified')
"""))
    for index,(new,old) in enumerate(substitutions):
        if source.count(new)!=1:raise AssertionError(f'Moving retirement inverse occurrence differs at {index}')
        source=source.replace(new,old,1)
    return source




def restore_runtime_failure_fix(source):
    """Reverse only the post-VM ownership and inherited-descriptor fixes."""
    fixed_gio="""        # The launched app inherits the helper's descriptors. Use the existing
        # regular-file GUI launch path so waiting for the helper cannot wait for
        # the long-lived Celluloid process to close a captured PIPE.
        self.launch(['/usr/bin/python3','-c',code,action])
        helper=self.launches[-1]
        try:
            returncode=helper.wait(timeout=15)
        except subprocess.TimeoutExpired:
            helper.terminate()
            try: helper.wait(timeout=2)
            except subprocess.TimeoutExpired: helper.kill();helper.wait(timeout=2)
            raise RuntimeError('Gio DesktopAppInfo action helper timed out') from None
        self.steps[-1].update(status='launch-helper-completed',returncode=returncode)
        require(returncode==0,'Gio DesktopAppInfo action launch failed')
"""
    old_gio="""        result=self.cmd(['/usr/bin/python3','-c',code,action],timeout=15)
        require(result[0]==0,'Gio DesktopAppInfo action launch failed')
"""
    owned_directory="""    def owned_media_directory(self):
        path=self.root/'media file opener'
        self.user_mkdir(path)
        info=path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid==self.uid
                and not info.st_mode&0o022 and path.resolve()==path,
                'file-manager media fixture directory owner/type differs')
        return path

"""
    replacements=((fixed_gio,old_gio),(owned_directory,''),
                  ("        media_dir=self.owned_media_directory()\n",
                   "        media_dir=self.root/'media file opener';media_dir.mkdir()\n"))
    for index,(new,old) in enumerate(replacements):
        if source.count(new)!=1:raise AssertionError(f'Runtime failure inverse occurrence differs at {index}')
        source=source.replace(new,old,1)
    return source


def restore_single_player_native(source):
    """Reverse only the one-player hard-fail gate for historical byte proofs."""
    source=restore_epiphany_product_route(source)
    source=restore_moving_player_retirement(source)
    source=restore_runtime_failure_fix(source)
    substitutions=(
        ("            require(1<=len(players)<=2,'controls trial primary player inventory differs')\n            for player in players: retire_renderer_player(player,self.uid)\n","            require(1<=len(players)<=3,'controls trial primary player inventory differs')\n            retired=[row['player'] for row in primary.get('player_attempts',[])\n                     if row.get('owned_player_cleanup_completed') is True]\n            require(len(retired)<=1 and all(sum((p.get('pid'),p.get('start_ticks'))==\n                    (old.get('pid'),old.get('start_ticks')) for p in players)==1 for old in retired),\n                    'controls trial prior retired player identity differs')\n            retired_keys={(p['pid'],p['start_ticks']) for p in retired}\n            for player in players:\n                if (player['pid'],player['start_ticks']) not in retired_keys:\n                    retire_renderer_player(player,self.uid)\n"),
        ('    def visual_media(self):\n        fixture,expected,source_sha=self.visual_fixture()\n        # This release gate admits exactly one fresh product-wrapper player.\n        # A failed or unmatched capture cannot create another acceptance path.\n        player_attempt=1\n        player_attempt_limit=1\n',"    def visual_media(self, restart=None):\n        player_attempt_limit=2\n        if restart is None:\n            fixture,expected,source_sha=self.visual_fixture()\n            restart=dict(fixture=fixture,expected=expected,source_sha=source_sha,player_attempts=[])\n        else:\n            require(type(restart) is dict and set(restart)=={'fixture','expected','source_sha','player_attempts'}\n                    and type(restart['player_attempts']) is list\n                    and len(restart['player_attempts'])==1,\n                    'visual player restart state differs')\n            fixture=restart['fixture']; expected=restart['expected']; source_sha=restart['source_sha']\n            require(digest(fixture)==restart['player_attempts'][0]['fixture_sha256']\n                    and digest(expected)==restart['player_attempts'][0]['expected_rgb_sha256']\n                    and source_sha==restart['player_attempts'][0]['input_rgb_sha256'],\n                    'visual player restart fixture identity differs')\n        player_attempt=len(restart['player_attempts'])+1\n        require(1<=player_attempt<=player_attempt_limit,'visual player restart limit exceeded')\n"),
        ("        ipc=self.root/'visual-reference-ipc.sock'\n","        ipc=self.root/('visual-reference-ipc-'+str(player_attempt)+'.sock')\n"),
        ("        renderer=self.product_renderer_contract(player) if getattr(self,'gui_v6',False) else None\n        self.wait(lambda:ipc.is_socket())\n        def ready_reference():\n","        renderer=self.product_renderer_contract(player) if getattr(self,'gui_v6',False) else None\n        require(not any((player['pid'],player['start_ticks'])==(row['player']['pid'],row['player']['start_ticks'])\n                        or player['client_id']==row['player']['client_id'] for row in restart['player_attempts']),\n                'visual restart did not create a fresh owned player')\n        self.wait(lambda:ipc.is_socket())\n        def ready_reference():\n"),
        ("        image=self.root/'celluloid-reference.png'\n","        image=self.root/('celluloid-reference.png' if player_attempt==1 else 'celluloid-reference-player-2.png')\n"),
        ('        attempt_limit=1\n','        attempt_limit=6\n'),
        ("        player_receipt={key:info[key] for key in ('player_attempt','player','player_state','fixture_sha256','input_rgb_sha256',\n            'expected_rgb_sha256','actual_rgb_sha256','playback_clock','capture_attempts','capture_attempt_limit',\n            'capture_deadline_seconds','accepted_capture_attempt','oracle','screenshot','product_renderer')}\n        player_receipt.update(owned_player_cleanup_completed=False,restart_eligible=False,release_acceptance=False)\n        info['player_attempts']=[player_receipt]\n        info['accepted_player_attempt']=1 if oracle.get('status')=='matched' else None\n        (self.root/'visual-oracle.json').write_text(json.dumps(info,indent=2))\n        self.trace('visual-oracle',proof=info)\n        if getattr(self,'gui_v6',False):\n            self.native_protocol_diagnostic(player,state,screenshot,client)\n            self.player_fullscreen(player,False)\n        require(info['oracle']['status']=='matched',\n                'actual static visual fixture content unmatched; rendered-content gate remains open')\n        return info\n","        restart_eligible=(player_attempt<player_attempt_limit and len(attempts)==attempt_limit\n                          and all(row.get('oracle',{}).get('status')=='unmatched' for row in attempts))\n        player_receipt={key:info[key] for key in ('player_attempt','player','player_state','fixture_sha256','input_rgb_sha256',\n            'expected_rgb_sha256','actual_rgb_sha256','playback_clock','capture_attempts','capture_attempt_limit',\n            'capture_deadline_seconds','accepted_capture_attempt','oracle','screenshot','product_renderer')}\n        player_receipt.update(owned_player_cleanup_completed=False,restart_eligible=restart_eligible,release_acceptance=False)\n        restart['player_attempts'].append(player_receipt)\n        info['player_attempts']=restart['player_attempts']\n        info['accepted_player_attempt']=player_attempt if oracle.get('status')=='matched' else None\n        (self.root/'visual-oracle.json').write_text(json.dumps(info,indent=2))\n        self.trace('visual-oracle',proof=info)\n        if getattr(self,'gui_v6',False) and not restart_eligible:\n            self.native_protocol_diagnostic(player,state,screenshot,client)\n        if getattr(self,'gui_v6',False):\n            self.player_fullscreen(player,False)\n        if restart_eligible:\n            if getattr(self,'gui_v6',False): self.finish_native_protocol()\n            try:\n                player_receipt['cleanup']=retire_reference_player(player,self.uid,ipc,self.root,player_attempt)\n                player_receipt['owned_player_cleanup_completed']=True\n            finally:\n                (self.root/'visual-oracle.json').write_text(json.dumps(info,indent=2))\n            return self.visual_media(restart)\n        if getattr(self,'gui_v6',False) and info['oracle']['status']=='unmatched':\n            self.controlled_controls_trials(fixture,expected,source_sha,info)\n        require(info['oracle']['status']=='matched','actual static visual fixture content unmatched; rendered-content gate remains open')\n        return info\n"),
        ('\n\nclass RendererTrialSmoke','\n\ndef retire_reference_player(proof,uid,ipc,root,attempt):\n    """Retire exactly one failed primary player before its sole fresh restart."""\n    require(type(attempt) is int and attempt==1 and isinstance(root,Path) and root.is_absolute()\n            and isinstance(ipc,Path) and ipc.parent==root and ipc.name==\'visual-reference-ipc-1.sock\',\n            \'visual restart cleanup target differs\')\n    retire_renderer_player(proof,uid)\n    removed=False\n    try:\n        info=ipc.lstat()\n        require(stat.S_ISSOCK(info.st_mode) and info.st_uid==uid,\n                \'visual restart IPC owner/type differs\')\n        ipc.unlink()\n        removed=True\n    except FileNotFoundError:\n        pass\n    require(not ipc.exists() and not ipc.is_symlink(),\'visual restart IPC cleanup incomplete\')\n    return dict(process_identity_retired=True,owned_ipc_absent=True,\n                owned_ipc_removed=removed,release_acceptance=False)\n\n\nclass RendererTrialSmoke'),
    )
    for index,(new,old) in enumerate(substitutions):
        if source.count(new)!=1:raise AssertionError(f'Single-player inverse occurrence differs at {index}')
        source=source.replace(new,old,1)
    if hashlib.sha256(source.encode()).hexdigest()!=TWO_PLAYER_CURRENT_SHA:
        raise AssertionError('Pre-single-player Native source differs')
    return source


def restore_audit_file_stream_native(source):
    source=restore_single_player_native(source)
    def replace_marked(text, start, end, replacement):
        if text.count(start) != 1 or text.count(end) != 1:
            raise AssertionError('Streaming audit file inverse marker differs')
        first = text.index(start)
        last = text.index(end, first) + len(end)
        return text[:first] + replacement + text[last:]

    source = replace_marked(source, '# BEGIN STREAMING_AUDIT_FILE_INTERVAL\n',
        '# END STREAMING_AUDIT_FILE_INTERVAL\n', '')
    old_verify = """def verify_security(before, after, journal_avcs, audit_messages=''):
    require(before['selinux'] == after['selinux'] == 'Enforcing', 'SELinux must remain Enforcing')
    require(after['audit']['enabled'] == before['audit']['enabled'], 'kernel audit mode changed during checks')
    require(after['audit']['lost'] == before['audit']['lost'], 'audit records were lost during checks')
    require(type(journal_avcs) is int and journal_avcs >= 0, 'invalid journal AVC projection')
    audit_avcs = sum(1 for line in audit_messages.splitlines() if AVC.search(line))
    require(journal_avcs + audit_avcs == 0, 'new AVC requires investigation')
    return dict(selinux=after['selinux'], audit=after['audit'], observed_new_avcs=0,
                audit_enabled=after['audit']['enabled'] in (1,2),
                scope='journal cursor and available audit-file interval; disabled kernel audit is a recorded telemetry limit')
"""
    source = replace_marked(source, '# BEGIN STREAMING_AUDIT_FILE_VERIFICATION\n',
        '# END STREAMING_AUDIT_FILE_VERIFICATION\n', old_verify)
    source = replace_marked(source, '\n\n# BEGIN STREAMING_AUDIT_FILE_SCANNER\n',
        '# END STREAMING_AUDIT_FILE_SCANNER\n\n\n', '\n\n')
    old_finish = """    def finish(self):
        after = self.state()
        journal = journal_avc_count(self.cursor, timeout=60)
        audit_messages = ''
        if self.audit_offset:
            info = self.audit_file.stat()
            dev, ino, offset = self.audit_offset
            require((info.st_dev, info.st_ino) == (dev, ino) and info.st_size >= offset,
                    'audit log rotated/truncated; interval must be reviewed separately')
            require(info.st_size - offset <= LIMIT, 'audit interval exceeded evidence bound')
            with self.audit_file.open('rb') as stream:
                stream.seek(offset)
                audit_messages = stream.read(LIMIT).decode(errors='replace')
        elif self.audit_file.exists():
            # The new file may include records not forwarded to the journal.
            require(self.audit_file.stat().st_size <= LIMIT, 'new audit log exceeded evidence bound')
            audit_messages = self.audit_file.read_text(errors='replace')
        return verify_security(self.before, after, journal['avcs'], audit_messages)
"""
    source = replace_marked(source, '    # BEGIN STREAMING_AUDIT_FILE_FINISH\n',
        '    # END STREAMING_AUDIT_FILE_FINISH\n', old_finish)
    if hashlib.sha256(source.encode()).hexdigest() != FRESH_PLAYER_RESTART_NATIVE_SHA:
        raise AssertionError('Pre-streaming-audit-file Native source differs')
    return source


def restore_product_launch_native(source):
    """Remove only the product-launch layer before historical inverse controls."""
    # Reverse the product route qualification added with the launcher. Each
    # boundary is unique so unrelated historical source remains byte-exact.
    start="        media_dir=self.root/'media file opener';media_dir.mkdir()\n"
    end="                    scope='actual role launch + PCManFM text/ZIP/media openers/F4 + GUI Unicode edit/save; mount/network/a11y remain separate')\n"
    if source.count(start)!=1 or source.count(end)!=1: raise AssertionError('Product file-manager inverse differs')
    a=source.index(start);z=source.index(end,a)+len(end)
    old=("        return dict(role_terminal=role_terminal,role_editor=editor,role_files=files,\n"
         "                    file_manager_foot=terminal,file_manager_zip_opener=archiver,\n"
         "                    terminal_execution=proof,gui_saved=dict(path=str(fixture),sha256=digest(fixture),bytes=len(wanted)),\n"
         "                    screenshots=[editor_shot,self.screenshot('files-opened-zip')],\n"
         "                    scope='actual role launch + PCManFM file opener/F4 + GUI Unicode edit/save; mount/network/a11y remain separate')\n")
    source=source[:a]+old+source[z:]
    start="        action_routes=[]\n";end="        ipc = self.root/'celluloid-ipc.sock'\n"
    if source.count(start)!=1 or source.count(end)!=1: raise AssertionError('Product action inverse differs')
    a=source.index(start);z=source.index(end,a)
    source=source[:a]+source[z:]
    new=("        return dict(moving_proof, visual_reference=visual,desktop_action_launches=action_routes,\n"
         "                    enqueue_semantics=enqueue_semantics,\n"
         "                    scope='product file-manager/MIME and Gio desktop actions plus enqueue semantics; original moving fixture lossless decode/advancing AV state and separate static rendered-content oracle; motion/perceived audio/hardware remain unqualified')\n")
    old=("        return dict(moving_proof, visual_reference=visual,\n"
         "                    scope='original moving fixture lossless decode/advancing AV state plus separate static rendered-content oracle; motion/perceived audio/hardware remain unqualified')\n")
    if source.count(new)!=1: raise AssertionError('Product media receipt inverse differs')
    source=source.replace(new,old,1)
    source=source.replace("require(self.native_physical_count<=7 and action in ('navigate','f4','open-first')",
                          "require(self.native_physical_count<=5 and action in ('navigate','f4','open-first')",1)
    source=source.replace("path in (str(self.root/'files with spaces'),str(self.root/'archive file opener'),str(self.root/'media file opener'))",
                          "path in (str(self.root/'files with spaces'),str(self.root/'archive file opener'))",1)
    start='    def product_launch_contract(self, player, route):\n'
    end='    def product_renderer_contract(self, player):\n'
    if source.count(start)!=1 or source.count(end)!=1: raise AssertionError('Product route helpers inverse differs')
    a=source.index(start);z=source.index(end,a)
    source=source[:a]+source[z:]
    replacements=(
        ("              'QT_QPA_PLATFORM', 'GDK_BACKEND', 'GSK_RENDERER', 'MANGO_SOCKET')\n",
         "              'QT_QPA_PLATFORM', 'GDK_BACKEND', 'MANGO_SOCKET')\n"),
        ("        # Exercise the installed product launcher. The private GTK diagnostic is\n"
         "        # mandatory because the environment request alone cannot prove realization.\n"
         "        require(argv[0]=='/usr/libexec/arctic/arctic-celluloid' and getattr(self,'gui_v6',False),\n"
         "                'native product Celluloid launcher selection differs')\n",
         "        # Only the already isolated static Celluloid, no renderer/command flag.\n"
         "        require(argv[0]=='/usr/bin/celluloid' and getattr(self,'gui_v6',False),\n"
         "                'native protocol diagnostic player selection differs')\n"),
        ('            drain=NativeProtocolDrain(renderer=True)\n','            drain=NativeProtocolDrain()\n'),
        ('            # Capture setup finishes before the product app is launched.\n',
         '            # Optional setup finishes before any diagnostic app is launched.\n'),
        ("            raise RuntimeError('product renderer attestation setup unavailable') from None\n",
         '            # A failed private capture setup uses the original, uninstrumented launch.\n'
         '            self.launch(argv); return\n'),
        ("                child=subprocess.Popen(self.prefix+['GSK_DEBUG=renderer','WAYLAND_DEBUG=client']+argv,\n"
         "                                       stdout=stream,stderr=writer)\n",
         "                child=subprocess.Popen(self.prefix+['WAYLAND_DEBUG=client']+argv,stdout=stream,stderr=writer)\n"),
        ("        player = self.fresh_window(lambda:self.launch_protocol_player(['/usr/libexec/arctic/arctic-celluloid','--no-existing-session',\n",
         "        player = self.fresh_window(lambda:self.launch(['/usr/bin/celluloid','--no-existing-session',\n"),
        ("        renderer=self.product_renderer_contract(player) if getattr(self,'gui_v6',False) else None\n",''),
        ("        renderer=self.product_renderer_contract(player) if getattr(self,'gui_v6',False) else None\n",''),
        ('                          product_renderer=renderer,\n',''),
        ("        if getattr(self,'gui_v6',False):\n"
         "            self.player_fullscreen(player,False)\n"
         "            self.finish_native_protocol()\n",
         "        if getattr(self,'gui_v6',False):\n"
         "            self.player_fullscreen(player,False)\n"),
        ("        diagnostic=isinstance(self,(RendererTrialSmoke,ControlsTrialSmoke))\n"
         "        expected='/usr/bin/celluloid' if diagnostic else '/usr/libexec/arctic/arctic-celluloid'\n"
         "        require(argv[0]==expected, 'reference controls Celluloid launcher selection differs')\n",
         "        require(argv[0]=='/usr/bin/celluloid', 'reference controls require Celluloid')\n"),
        ("        player=self.fresh_window(lambda:self.launch_reference_player(['/usr/libexec/arctic/arctic-celluloid','--no-existing-session',\n",
         "        player=self.fresh_window(lambda:self.launch_reference_player(['/usr/bin/celluloid','--no-existing-session',\n"),
        ('                  product_renderer=renderer,\n',''),
        ("            'capture_deadline_seconds','accepted_capture_attempt','oracle','screenshot','product_renderer')}\n",
         "            'capture_deadline_seconds','accepted_capture_attempt','oracle','screenshot')}\n"),
    )
    for new,old in replacements:
        if new not in source: raise AssertionError('Product launch inverse occurrence differs')
        source=source.replace(new,old,1)
    start='    def product_renderer_contract(self, player):\n'
    end='    def native_protocol_diagnostic(self, player, state, screenshot, client):\n'
    if source.count(start)!=1 or source.count(end)!=1: raise AssertionError('Product renderer inverse block differs')
    a=source.index(start);z=source.index(end,a)
    source=source[:a]+source[z:]
    if hashlib.sha256(source.encode()).hexdigest()!=PRE_PRODUCT_LAUNCH_NATIVE_SHA:
        raise AssertionError('Pre-product-launch Native source differs')
    return source


def restore_fresh_player_restart_native(source):
    source=restore_audit_file_stream_native(source)
    if hashlib.sha256(source.encode()).hexdigest()!=FRESH_PLAYER_RESTART_NATIVE_SHA:
        raise AssertionError('Fresh player restart Native source differs')
    source=restore_product_launch_native(source)
    substitutions=(("""    def visual_media(self, restart=None):
        player_attempt_limit=2
        if restart is None:
            fixture,expected,source_sha=self.visual_fixture()
            restart=dict(fixture=fixture,expected=expected,source_sha=source_sha,player_attempts=[])
        else:
            require(type(restart) is dict and set(restart)=={'fixture','expected','source_sha','player_attempts'}
                    and type(restart['player_attempts']) is list
                    and len(restart['player_attempts'])==1,
                    'visual player restart state differs')
            fixture=restart['fixture']; expected=restart['expected']; source_sha=restart['source_sha']
            require(digest(fixture)==restart['player_attempts'][0]['fixture_sha256']
                    and digest(expected)==restart['player_attempts'][0]['expected_rgb_sha256']
                    and source_sha==restart['player_attempts'][0]['input_rgb_sha256'],
                    'visual player restart fixture identity differs')
        player_attempt=len(restart['player_attempts'])+1
        require(1<=player_attempt<=player_attempt_limit,'visual player restart limit exceeded')
""","""    def visual_media(self):
        fixture,expected,source_sha=self.visual_fixture()
"""),("        ipc=self.root/('visual-reference-ipc-'+str(player_attempt)+'.sock')\n",
              "        ipc=self.root/'visual-reference-ipc.sock'\n"),("        image=self.root/('celluloid-reference.png' if player_attempt==1 else 'celluloid-reference-player-2.png')\n",
              "        image=self.root/'celluloid-reference.png'\n"),("""        require(not any((player['pid'],player['start_ticks'])==(row['player']['pid'],row['player']['start_ticks'])
                        or player['client_id']==row['player']['client_id'] for row in restart['player_attempts']),
                'visual restart did not create a fresh owned player')
""",''),("                  player_attempt=player_attempt,player_attempt_limit=player_attempt_limit,\n",''),("""        restart_eligible=(player_attempt<player_attempt_limit and len(attempts)==attempt_limit
                          and all(row.get('oracle',{}).get('status')=='unmatched' for row in attempts))
        player_receipt={key:info[key] for key in ('player_attempt','player','player_state','fixture_sha256','input_rgb_sha256',
            'expected_rgb_sha256','actual_rgb_sha256','playback_clock','capture_attempts','capture_attempt_limit',
            'capture_deadline_seconds','accepted_capture_attempt','oracle','screenshot')}
        player_receipt.update(owned_player_cleanup_completed=False,restart_eligible=restart_eligible,release_acceptance=False)
        restart['player_attempts'].append(player_receipt)
        info['player_attempts']=restart['player_attempts']
        info['accepted_player_attempt']=player_attempt if oracle.get('status')=='matched' else None
""",''),("        if getattr(self,'gui_v6',False) and not restart_eligible:\n",
              "        if getattr(self,'gui_v6',False):\n"),("""        if restart_eligible:
            if getattr(self,'gui_v6',False): self.finish_native_protocol()
            try:
                player_receipt['cleanup']=retire_reference_player(player,self.uid,ipc,self.root,player_attempt)
                player_receipt['owned_player_cleanup_completed']=True
            finally:
                (self.root/'visual-oracle.json').write_text(json.dumps(info,indent=2))
            return self.visual_media(restart)
""",''),("            require(1<=len(players)<=3,'controls trial primary player inventory differs')\n",
              "            require(1<=len(players)<=2,'controls trial primary player inventory differs')\n"),("""            retired=[row['player'] for row in primary.get('player_attempts',[])
                     if row.get('owned_player_cleanup_completed') is True]
            require(len(retired)<=1 and all(sum((p.get('pid'),p.get('start_ticks'))==
                    (old.get('pid'),old.get('start_ticks')) for p in players)==1 for old in retired),
                    'controls trial prior retired player identity differs')
            retired_keys={(p['pid'],p['start_ticks']) for p in retired}
            for player in players:
                if (player['pid'],player['start_ticks']) not in retired_keys:
                    retire_renderer_player(player,self.uid)
""","            for player in players: retire_renderer_player(player,self.uid)\n"),("""def retire_reference_player(proof,uid,ipc,root,attempt):
    \"\"\"Retire exactly one failed primary player before its sole fresh restart.\"\"\"
    require(type(attempt) is int and attempt==1 and isinstance(root,Path) and root.is_absolute()
            and isinstance(ipc,Path) and ipc.parent==root and ipc.name=='visual-reference-ipc-1.sock',
            'visual restart cleanup target differs')
    retire_renderer_player(proof,uid)
    removed=False
    try:
        info=ipc.lstat()
        require(stat.S_ISSOCK(info.st_mode) and info.st_uid==uid,
                'visual restart IPC owner/type differs')
        ipc.unlink()
        removed=True
    except FileNotFoundError:
        pass
    require(not ipc.exists() and not ipc.is_symlink(),'visual restart IPC cleanup incomplete')
    return dict(process_identity_retired=True,owned_ipc_absent=True,
                owned_ipc_removed=removed,release_acceptance=False)


""",''))
    for index,(new,old) in enumerate(substitutions):
        if source.count(new)!=1:raise AssertionError(f'Fresh player restart inverse occurrence differs at {index}')
        source=source.replace(new,old,1)
    if hashlib.sha256(source.encode()).hexdigest()!=BOUNDED_RETRY_NATIVE_SHA:
        raise AssertionError('Pre-fresh-player-restart Native source differs')
    return source


def restore_bounded_retry_native(source):
    source=restore_fresh_player_restart_native(source)
    if hashlib.sha256(source.encode()).hexdigest()!=BOUNDED_RETRY_NATIVE_SHA:
        raise AssertionError('Bounded retry Native source differs')
    retry_current="""        attempt_limit=6
        capture_command_timeout_seconds=3
        retry_settle_seconds=.5
        capture_deadline_seconds=(attempt_limit * 2 * capture_command_timeout_seconds
                                  + (attempt_limit-1) * retry_settle_seconds + 3.5)
        capture_deadline=time.monotonic()+capture_deadline_seconds
"""
    retry_original="""        capture_deadline=time.monotonic()+8
        attempt_limit=6
"""
    receipt="""            # Preserve bounded, content-free attempt evidence even when a later
            # deadline check fails before the final full oracle is assembled.
            (self.root/'visual-oracle.json').write_text(json.dumps(dict(
                schema='arctic-native-visual-attempts-v1',release_acceptance=False,
                capture_attempts=attempts,capture_attempt_limit=attempt_limit,
                capture_deadline_seconds=capture_deadline_seconds),indent=2)+'\\n')
"""
    if source.count(retry_current)!=1 or source.count(receipt)!=1:
        raise AssertionError('Bounded retry inverse additions differ')
    source=source.replace(retry_current,retry_original,1).replace(receipt,'',1)
    source=source.replace('time.sleep(retry_settle_seconds)','time.sleep(.5)',1)
    source=source.replace('min(capture_command_timeout_seconds,remaining)','min(3,remaining)',2)
    source=source.replace('capture_deadline_seconds=capture_deadline_seconds,','capture_deadline_seconds=8,',1)
    if hashlib.sha256(source.encode()).hexdigest()!=STREAM_NATIVE_SHA:
        raise AssertionError('Pre-bounded-retry Native source differs')
    return source


def restore_security_stream_native(source):
    source=restore_bounded_retry_native(source)
    if hashlib.sha256(source.encode()).hexdigest()!=STREAM_NATIVE_SHA:
        raise AssertionError('Streaming journal Native source differs')
    constants = ('JOURNAL_LINE_LIMIT = 1024 * 1024\n'
                 'JOURNAL_RECORD_LIMIT = 250000\n'
                 'JOURNAL_STDERR_LIMIT = 64 * 1024\n'
                 'JOURNAL_READ_SIZE = 64 * 1024\n')
    if source.count(constants)!=1:raise AssertionError('Streaming journal constants differ')
    source=source.replace(constants,'')
    a=source.index('def _unique_json_object');z=source.index('class SecurityInterval:',a)
    source=source[:a]+"def verify_security(before, after, new_messages):\n    require(before['selinux'] == after['selinux'] == 'Enforcing', 'SELinux must remain Enforcing')\n    require(after['audit']['enabled'] == before['audit']['enabled'], 'kernel audit mode changed during checks')\n    require(after['audit']['lost'] == before['audit']['lost'], 'audit records were lost during checks')\n    denied = [line for line in new_messages.splitlines() if AVC.search(line)]\n    require(not denied, 'new AVC requires investigation: ' + '\\n'.join(denied[:20]))\n    return dict(selinux=after['selinux'], audit=after['audit'], observed_new_avcs=0,\n                audit_enabled=after['audit']['enabled'] in (1,2),\n                scope='journal cursor and available audit-file interval; disabled kernel audit is a recorded telemetry limit')\n\n\n"+source[z:]
    a=source.index('    def finish(self):',source.index('class SecurityInterval:'))
    z=source.index('\ndef discover_desktop',a)
    source=source[:a]+"    def finish(self):\n        after = self.state()\n        journal = execute(['journalctl', '-b', '--no-pager', '--after-cursor', self.cursor,\n                           '-o', 'json'], timeout=60)[1]\n        messages = '\\n'.join(str(json.loads(line).get('MESSAGE', ''))\n                             for line in journal.splitlines() if line)\n        if self.audit_offset:\n            info = self.audit_file.stat()\n            dev, ino, offset = self.audit_offset\n            require((info.st_dev, info.st_ino) == (dev, ino) and info.st_size >= offset,\n                    'audit log rotated/truncated; interval must be reviewed separately')\n            require(info.st_size - offset <= LIMIT, 'audit interval exceeded evidence bound')\n            with self.audit_file.open('rb') as stream:\n                stream.seek(offset)\n                messages += '\\n' + stream.read(LIMIT).decode(errors='replace')\n        elif self.audit_file.exists():\n            # The new file may include records not forwarded to the journal.\n            require(self.audit_file.stat().st_size <= LIMIT, 'new audit log exceeded evidence bound')\n            messages += '\\n' + self.audit_file.read_text(errors='replace')\n        return verify_security(self.before, after, messages)\n\n"+source[z:]
    if hashlib.sha256(source.encode()).hexdigest()!=PRE_STREAM_NATIVE_SHA:
        raise AssertionError('Pre-streaming Native source differs')
    return source


def restore_controls_native(source):
    source=restore_security_stream_native(source)
    for start,end in (
        ('    # BEGIN CONTROLLED_CONTROLS_INVOCATION\n','    # END CONTROLLED_CONTROLS_INVOCATION\n\n'),
        ('# BEGIN CONTROLLED_CONTROLS_STUDY\n','# END CONTROLLED_CONTROLS_STUDY\n\n\n'),
    ):
        if source.count(start)!=1 or source.count(end)!=1:raise AssertionError('Controls inverse markers differ')
        a=source.index(start);z=source.index(end,a)+len(end);source=source[:a]+source[z:]
    new='            self.controlled_controls_trials(fixture,expected,source_sha,info)\n'
    if source.count(new)!=1:raise AssertionError('Controls inverse call differs')
    source=source.replace(new,'            self.controlled_renderer_trials(fixture,expected,source_sha,info)\n')
    if hashlib.sha256(source.encode()).hexdigest()!=BASE_NATIVE_SHA:raise AssertionError('Original whole Native source differs')
    return source


def restore_controls_guest(source):
    failure_headroom="""                    # A failed gate adds one owned failure screenshot after the
                    # normal navigation diagnostics.  Keep the strict 16 MiB
                    # transport ceiling and prioritize that failure frame plus
                    # the primary role/media/oracle artifacts needed to diagnose
                    # it.  Passing runs retain their original byte-for-byte
                    # inventory, and private profile paths remain excluded above.
                    if (type(report) is dict and report.get('status') == 'failed'
                            and relative.startswith('gui-') and relative.endswith('.png')
                            and '-failure-' not in relative):
                        continue
"""
    if source.count(failure_headroom)!=1:
        raise AssertionError('Failure evidence headroom inverse occurrence differs')
    source=source.replace(failure_headroom,'',1)
    native=(HERE/'native_smoke.py').read_text()
    boundary='\n\n# BEGIN NATIVE_BULK_TRANSPORT\n'
    original=restore_controls_native(native)
    if not source.startswith(native[:native.index('def main():\n')]):raise AssertionError('Controls guest prefix differs')
    # The bundle inherits the original Native prefix through run_checks, then
    # the original bulk/export entrypoint. No off-branch Git object is required.
    head=native[:native.index('def main():\n')]
    source=original[:original.index('def main():\n')]+source[len(head):]
    substitutions=(
        ('for index in range(15)  # Seven one-use gate failures plus eight GUI diagnostics.',
         'for index in range(13)  # Seven one-use gate failures plus six GUI diagnostics.'),
        ("        'media-fixture-before-location', 'media-fixture-navigation-confirmed',\n",''),
        ('0-controls-state-trials.json','0-controlled-renderer-trials.json'),
        ('controls-trial-transition/reference.png','renderer-trial-default/reference.png'),
        ('controls-trial-hidden/reference.png','renderer-trial-gl/reference.png'),
        (hashlib.sha256(native.encode()).hexdigest(),BASE_NATIVE_SHA),
    )
    for index,(new,old) in enumerate(substitutions):
        if source.count(new)!=1:raise AssertionError(f'Controls guest inverse occurrence differs at {index}')
        source=source.replace(new,old)
    if hashlib.sha256(source.encode()).hexdigest()!=BASE_GUEST_SHA:raise AssertionError('Original whole guest differs')
    return source


class ControlsStateTrials(unittest.TestCase):
    def parent(self,root):
        config=root/'config';config.mkdir(mode=0o700)
        return Mock(root=root,user=pwd.getpwuid(os.getuid()),uid=os.getuid(),stage='live',
                    prefix=['synthetic-owned-prefix','XDG_CONFIG_HOME='+str(config)],
                    original_prefix=['synthetic-owned-prefix'])

    def test_media_fixture_directory_is_created_by_and_guarded_for_desktop_uid(self):
        with tempfile.TemporaryDirectory() as temporary:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(temporary);smoke.uid=os.getuid()
            smoke.cmd=Mock(side_effect=lambda argv:Path(argv[-1]).mkdir(mode=0o700))
            path=smoke.owned_media_directory()
            self.assertEqual(path,smoke.root/'media file opener')
            self.assertEqual(path.stat().st_uid,smoke.uid)
            smoke.cmd.assert_called_once_with(['mkdir','-p',str(path)])
        with tempfile.TemporaryDirectory() as temporary:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(temporary);smoke.uid=os.getuid()
            def writable(argv):
                Path(argv[-1]).mkdir();Path(argv[-1]).chmod(0o777)
            smoke.cmd=Mock(side_effect=writable)
            with self.assertRaisesRegex(RuntimeError,'directory owner/type differs'):
                smoke.owned_media_directory()

    def test_gio_action_helper_uses_regular_file_descriptors_and_launches_once(self):
        with tempfile.TemporaryDirectory() as temporary:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(temporary)
            smoke.prefix=['runuser','-u','fixture','--','env'];smoke.launches=[];smoke.steps=[]
            helper=Mock();helper.wait.return_value=0
            with patch.object(N.subprocess,'Popen',return_value=helper) as popen:
                smoke.gio_desktop_action('new-window')
            popen.assert_called_once()
            argv=popen.call_args.args[0]
            self.assertEqual(argv.count('/usr/bin/python3'),1)
            self.assertEqual(argv[-1],'new-window')
            self.assertIs(popen.call_args.kwargs['stdout'],popen.call_args.kwargs['stderr'])
            self.assertIsNot(popen.call_args.kwargs['stdout'],subprocess.PIPE)
            helper.wait.assert_called_once_with(timeout=15)
            self.assertEqual(smoke.steps,[dict(argv=argv[len(smoke.prefix):],
                status='launch-helper-completed',log=str(smoke.root/'gui-launch-0.log'),returncode=0)])

    def test_gio_action_helper_timeout_fails_without_second_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=Path(temporary)
            smoke.prefix=['runuser','-u','fixture','--','env'];smoke.launches=[];smoke.steps=[]
            helper=Mock();helper.wait.side_effect=[subprocess.TimeoutExpired('helper',15),0]
            with patch.object(N.subprocess,'Popen',return_value=helper) as popen, \
                    self.assertRaisesRegex(RuntimeError,'action helper timed out'):
                smoke.gio_desktop_action('enqueue')
            popen.assert_called_once();helper.terminate.assert_called_once();helper.kill.assert_not_called()

    def test_whole_source_guest_and_unchanged_capture_oracle_rollback(self):
        new=(HERE/'native_smoke.py').read_text();old=restore_controls_native(new)
        restored=restore_controls_guest((HERE/'guest-check-native-v6.py').read_text())
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),BASE_GUEST_SHA)
        def segment(text,name,klass=None):
            nodes=ast.parse(text).body
            if klass:nodes=next(n for n in nodes if isinstance(n,ast.ClassDef) and n.name==klass).body
            return ast.get_source_segment(text,next(n for n in nodes if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name))
        for name in ('visual_reference_frame','evaluate_reference_rgb','visual_capture_geometry','mpv_property','mpv_hide_reference_controls'):
            self.assertEqual(segment(new,name),segment(old,name))
        self.assertEqual(segment(new,'RendererTrialSmoke'),segment(old,'RendererTrialSmoke'))
        for name in ('hide_reference_controls','cleanup','setup'):
            self.assertEqual(segment(new,name,'Smoke'),segment(old,name,'Smoke'))
        bounded=restore_bounded_retry_native(new)
        self.assertEqual(segment(bounded,'visual_media','Smoke').replace('self.controlled_controls_trials(', 'self.controlled_renderer_trials('),segment(old,'visual_media','Smoke'))
        for text in (new.replace("time.sleep(.5)","time.sleep(.6)",1),
                     new.replace('(attempt_limit-1) * retry_settle_seconds + 3.5',
                                 '(attempt_limit-1) * retry_settle_seconds + 4.5',1),
                     new.replace("schema='arctic-native-visual-attempts-v1'",
                                 "schema='arctic-native-visual-attempts-mutated'",1),
                     new+'\n# unknown mutation\n'):
            with self.assertRaises(AssertionError):restore_controls_native(text)

    def test_private_seed_exact_commands_and_nonzero_or_poison_readbacks_abort(self):
        for state in ('transition','hidden'):
            with tempfile.TemporaryDirectory() as temporary:
                trial=N.ControlsTrialSmoke(self.parent(Path(temporary)),state)
                wanted='true' if state=='transition' else 'false'
                trial.cmd=Mock(side_effect=[(0,'',''),(0,wanted,'')])
                proof=trial.seed_controls()
                self.assertEqual(proof['initial_visible'],state=='transition')
                calls=[c.args[0] for c in trial.cmd.call_args_list]
                prefix=['/usr/bin/env','GSETTINGS_BACKEND=keyfile','/usr/bin/gsettings']
                schema=['io.github.celluloid-player.Celluloid.window-state','show-controls']
                self.assertEqual(calls,[prefix+['set']+schema+[wanted],prefix+['get']+schema])
                for call in trial.cmd.call_args_list:self.assertEqual(call.kwargs['timeout'],5)
                for replies in ([(1,'','')],[(0,'',''),(1,wanted,'')],[(0,'',''),(0,'maybe','')],[(0,'',''),(0,'false' if wanted=='true' else 'true','')]):
                    trial.cmd=Mock(side_effect=replies)
                    with self.assertRaises(RuntimeError):trial.seed_controls()
                trial.prefix.append('GSETTINGS_BACKEND=dconf');trial.cmd=Mock()
                with self.assertRaises(RuntimeError):trial.seed_controls()
                trial.cmd.assert_not_called()

    def test_private_seed_foreign_directory_symlink_and_write_permission_reject(self):
        for poison in ('foreign','symlink','writable'):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);trial=N.ControlsTrialSmoke(self.parent(root),'hidden');trial.cmd=Mock()
                config=root/'config'
                if poison=='foreign':
                    other=root/'other';other.mkdir(mode=0o700);trial.prefix[-1]='XDG_CONFIG_HOME='+str(other)
                elif poison=='symlink':
                    config.rmdir();other=root/'other';other.mkdir();config.symlink_to(other)
                else:config.chmod(0o777)
                with self.assertRaises(RuntimeError):trial.seed_controls()
                trial.cmd.assert_not_called()

    def test_same_owned_default_launcher_and_half_second_capture_for_both_states(self):
        for state in ('transition','hidden'):
            with tempfile.TemporaryDirectory() as temporary:
                trial=N.ControlsTrialSmoke(self.parent(Path(temporary)),state);drain=Mock()
                with patch.object(N,'NativeProtocolDrain',return_value=drain),patch.object(N.subprocess,'Popen',return_value=Mock()) as popen:
                    trial.launch_reference_player(['/usr/bin/celluloid','--no-existing-session','--new-window','same-fixture'],trial.launch_renderer)
                argv=popen.call_args.args[0]
                self.assertEqual(argv[:3],['synthetic-owned-prefix',trial.prefix[1],'GSETTINGS_BACKEND=keyfile'])
                self.assertEqual(argv[3:9],['env','-u','GSK_RENDERER','GSK_DEBUG=renderer','WAYLAND_DEBUG=client','/usr/bin/celluloid'])
                self.assertNotIn('GSK_RENDERER=gl',argv);self.assertNotIn('GSETTINGS_BACKEND=keyfile',trial.prefix)
                drain.start.call_args.args[0].close()
        method=ast.get_source_segment((HERE/'native_smoke.py').read_text(),next(n for n in ast.parse((HERE/'native_smoke.py').read_text()).body if isinstance(n,ast.ClassDef) and n.name=='RendererTrialSmoke'))
        self.assertEqual(method.count('time.sleep(.5)'),1)
        self.assertLess(method.index('self.hide_reference_controls(player,ipc)'),method.index('time.sleep(.5)'))
        self.assertLess(method.index('time.sleep(.5)'),method.index("['grim'"))

    def test_bound_actual_action_readback_must_match_seed_and_hidden_state(self):
        for state in ('transition','hidden'):
            with tempfile.TemporaryDirectory() as temporary:
                trial=N.ControlsTrialSmoke(self.parent(Path(temporary)),state)
                good=dict(before_visible=state=='transition',after_visible=False,private_config_process_bound=True)
                with patch.object(N.Smoke,'hide_reference_controls',return_value=good):
                    self.assertEqual(trial.hide_reference_controls({},'owned.sock'),good)
                for poison in (dict(before_visible=not good['before_visible']),dict(before_visible=1),dict(after_visible=True),dict(private_config_process_bound=False)):
                    with patch.object(N.Smoke,'hide_reference_controls',return_value=dict(good,**poison)),self.assertRaises(RuntimeError):
                        trial.hide_reference_controls({},'owned.sock')

    def test_seed_failure_aborts_before_launch_and_retains_primary_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            trial=N.ControlsTrialSmoke(self.parent(Path(temporary)),'transition')
            trial.seed_controls=Mock(side_effect=RuntimeError('private source-known failure'))
            with patch.object(N.RendererTrialSmoke,'observe') as launch:
                with self.assertRaises(RuntimeError):trial.observe('fixture','expected','a'*64)
                launch.assert_not_called()

    def test_actual_observe_runs_seed_bound_hide_half_second_and_unchanged_rgb_oracle(self):
        for state,palette in (('transition',True),('hidden',True),('hidden',False)):
            with self.subTest(state=state,palette=palette),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);trial=N.ControlsTrialSmoke(self.parent(root),state)
                fixture=root/'fixture';fixture.write_bytes(b'source-fixed-synthetic-media')
                expected=root/'expected';expected.write_bytes(N.visual_reference_frame())
                pixels=expected.read_bytes() if palette else b'\0'*(160*120*3)
                player=dict(pid=71,start_ticks=3,client_id='10',executable='/usr/bin/celluloid',
                            executable_sha256='a'*64,is_xwayland=False)
                client=dict(id=10,pid=71,appid='celluloid',foreign_toplevel_id='owned',
                    x=0,y=0,width=160,height=120,monitor='synthetic-monitor',
                    is_focused=True,is_visible=True,is_fullscreen=True)
                monitors=dict(monitors=[dict(name='synthetic-monitor',x=0,y=0,width=160,height=120,scale=1,is_hdr=False)])
                environ=root/'synthetic-proc'/'71'/'environ';environ.parent.mkdir(parents=True)
                environ.write_bytes(b'GSETTINGS_BACKEND=keyfile\0XDG_CONFIG_HOME='+os.fsencode(root/'config')+b'\0')
                selected={'show-controls':None};events=[]
                trial.fresh_window=Mock(return_value=player);trial.alive=Mock(return_value=client);trial.fullscreen=Mock()
                trial.gtk_binding=Mock(return_value=dict(package='gtk4',version='4.22.5',mapped_library_sha256='b'*64))
                trial.native_protocol_drain=Mock(bind=Mock(return_value=True),snapshot=Mock(return_value=dict(
                    realized_renderer=dict(status='reported-realized',renderer='vulkan',release_acceptance=False,
                        video_widget_or_framebuffer_attested=False))))
                def command(argv,**kwargs):
                    if argv[:3]==['/usr/bin/env','GSETTINGS_BACKEND=keyfile','/usr/bin/gsettings']:
                        events.append(argv[3])
                        if argv[3]=='set':selected['show-controls']=argv[-1];return 0,'',''
                        return 0,selected['show-controls'],''
                    if argv[:3]==['mmsg','get','all-monitors']:return 0,json.dumps(monitors),''
                    if argv[:2]==['mmsg','dispatch']:return 0,'{"success":true}',''
                    if argv[0]=='grim':
                        events.append('capture')
                        def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
                        scan=b''.join(b'\0'+pixels[y*160*3:(y+1)*160*3] for y in range(120))
                        Path(argv[-1]).write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',160,120,8,2,0,0,0))
                            +chunk(b'IDAT',zlib.compress(scan))+chunk(b'IEND',b''))
                        return 0,'',''
                    if argv[0]=='ffmpeg':Path(argv[-1]).write_bytes(pixels);return 0,'',''
                    raise AssertionError('Unexpected fixture command')
                trial.cmd=Mock(side_effect=command)
                media={'path':str(fixture),'pause':False,'video-params':dict(w=160,h=120),'current-vo':'libmpv','time-pos':.7}
                endpoint=socket.socket(socket.AF_UNIX);endpoint.bind(str(trial.root/'player.sock'))
                def action(*args):events.append('bound-hide-action');selected['show-controls']='false'
                def slept(seconds):self.assertEqual(seconds,.5);events.append('settle')
                original_path=Path
                def mapped(value):return original_path(root/'synthetic-proc' if str(value)=='/proc' else value)
                try:
                    with patch.object(N,'Path',side_effect=mapped),patch.object(N,'mpv_property',side_effect=lambda path,key,pid,uid:media[key]), \
                            patch.object(N,'mpv_hide_reference_controls',side_effect=action),patch.object(N.time,'sleep',side_effect=slept):
                        value=trial.observe(fixture,expected,'c'*64)
                    self.assertEqual(value['oracle']['status'],'matched' if palette else 'unmatched')
                    self.assertEqual(value['capture_precondition']['before_visible'],state=='transition')
                    self.assertFalse(value['capture_precondition']['after_visible'])
                    self.assertTrue(value['capture_precondition']['private_config_process_bound'])
                    self.assertEqual(value['intervention'],state)
                    self.assertEqual(value['capture']['path'],'controls-trial-'+state+'/reference.png')
                    self.assertEqual(value['requested_gsk_renderer'],'unset');self.assertIsNone(value['requested_renderer_matched'])
                    self.assertFalse(value['release_acceptance']);self.assertFalse(value['rendering_cause_proven'])
                    self.assertLess(events.index('set'),events.index('bound-hide-action'))
                    self.assertLess(events.index('bound-hide-action'),events.index('settle'))
                    self.assertLess(events.index('settle'),events.index('capture'))
                finally:endpoint.close()

    def study(self,root,trials):
        fixture=root/'same-fixture';fixture.write_bytes(b'source-owned synthetic fixed fixture')
        expected=root/'expected';expected.write_bytes(N.visual_reference_frame())
        smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.stage='live'
        smoke.owned=[dict(executable='/usr/bin/celluloid',pid=11,start_ticks=1)];smoke.launches=[];smoke.finish_native_protocol=Mock()
        smoke.gates=[dict(check='open-codec-content-and-player-state',status='failed',detail='original primary failure')]
        primary=dict(oracle=dict(status='unmatched'),screenshot=dict(sha256='a'*64),capture_precondition=dict(before_visible=True,after_visible=False),
                     fixture_sha256=N.digest(fixture),expected_rgb_sha256=N.digest(expected))
        before=copy.deepcopy((smoke.gates,primary))
        with patch.object(N,'ControlsTrialSmoke',side_effect=trials) as constructor,patch.object(N,'retire_renderer_player'):
            smoke.controlled_controls_trials(fixture,expected,'b'*64,primary)
        self.assertEqual((smoke.gates,primary),before)
        return json.loads((root/'0-controls-state-trials.json').read_bytes()),constructor

    def test_actual_two_arm_glue_preserves_primary_and_fixed_order_no_extra_slots(self):
        with tempfile.TemporaryDirectory() as temporary:
            trials=[Mock(owned=[],launches=[],observe=Mock(return_value=dict(intervention=state,status='observed',
                player=dict(pid=20+i,start_ticks=2+i),oracle=dict(status='matched'),release_acceptance=False))) for i,state in enumerate(('transition','hidden'))]
            value,constructor=self.study(Path(temporary),trials)
            self.assertEqual([c.args[1] for c in constructor.call_args_list],['transition','hidden'])
            self.assertTrue(value['primary_failure_preserved']);self.assertFalse(value['release_acceptance'])
            self.assertFalse(value['rendering_cause_proven']);self.assertEqual(value['controls']['initial_controls_visible'],[True,False])
            self.assertEqual(value['controls']['diagnostic_time_bound_seconds_each'],120)
            self.assertEqual([r['status'] for r in value['trials']],['observed','observed'])
            self.assertEqual(set(p.name for p in Path(temporary).glob('0-*.json')),{'0-controls-state-trials.json'})

    def test_optional_failure_diagnostics_retire_the_single_primary_player(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);fixture=root/'same-fixture';fixture.write_bytes(b'fixed')
            expected=root/'expected';expected.write_bytes(N.visual_reference_frame())
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.stage='live';smoke.launches=[]
            players=[dict(executable='/usr/bin/celluloid',pid=11+i,start_ticks=21+i) for i in range(2)]
            smoke.owned=players;smoke.finish_native_protocol=Mock()
            primary=dict(oracle=dict(status='unmatched'),screenshot=dict(sha256='a'*64),
                capture_precondition=dict(before_visible=False,after_visible=False),fixture_sha256=N.digest(fixture),
                expected_rgb_sha256=N.digest(expected),player_attempts=[dict(player=players[1],owned_player_cleanup_completed=False)])
            trials=[Mock(owned=[],launches=[],observe=Mock(return_value=dict(player=dict(pid=30+i,start_ticks=40+i),
                    status='observed'))) for i in range(2)]
            retired=[]
            with patch.object(N,'ControlsTrialSmoke',side_effect=trials),patch.object(N,'retire_renderer_player',side_effect=lambda p,u:retired.append(p)):
                smoke.controlled_controls_trials(fixture,expected,'b'*64,primary)
            self.assertEqual(retired,players)

    def test_actual_primary_capture_hard_fails_without_acceptance_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);fixture=root/'fixture';fixture.write_bytes(b'source-fixed-synthetic-media')
            expected=root/'expected';expected.write_bytes(N.visual_reference_frame())
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.gui_v6=True;smoke.owned=[]
            smoke.visual_fixture=Mock(return_value=(fixture,expected,'c'*64));smoke.trace=Mock()
            players=[dict(pid=71,start_ticks=3,client_id='10',executable='/usr/bin/celluloid',
                          executable_sha256='a'*64)]
            def client(player):return dict(id=int(player['client_id']),pid=player['pid'],x=0,y=0,width=160,height=120,
                        monitor='synthetic-monitor',is_focused=True,is_visible=True,is_fullscreen=True)
            monitors=dict(monitors=[dict(name='synthetic-monitor',x=0,y=0,width=160,height=120,scale=1,is_hdr=False)])
            smoke.fresh_window=Mock(side_effect=lambda *args:(smoke.owned.append(players.pop(0)) or smoke.owned[-1]));smoke.alive=Mock(side_effect=lambda player:client(player))
            smoke.player_fullscreen=Mock();smoke.fullscreen_capture_pair=Mock();smoke.native_protocol_diagnostic=Mock()
            smoke.product_renderer_contract=Mock(return_value=dict(requested_renderer='gl',realized_renderer='gl'))
            smoke.hide_reference_controls=Mock(return_value=dict(before_visible=True,after_visible=False))
            smoke.controlled_controls_trials=Mock(return_value=dict(oracle=dict(status='matched'),release_acceptance=False))
            smoke.controlled_renderer_trials=Mock()
            smoke.wait=lambda fn,*args:fn()
            def command(argv,**kwargs):
                if argv[:3]==['mmsg','get','all-monitors']:return 0,json.dumps(monitors),''
                if argv[:2]==['mmsg','dispatch']:return 0,'{"success":true}',''
                if argv[0]=='grim':
                    Path(argv[-1]).write_bytes(b'\x89PNG\r\n\x1a\n'+struct.pack('>I',13)+b'IHDR'+struct.pack('>II',160,120))
                    return 0,'',''
                if argv[0]=='ffmpeg':Path(argv[-1]).write_bytes(b'\0'*(160*120*3));return 0,'',''
                raise AssertionError('Unexpected fixture command')
            smoke.cmd=Mock(side_effect=command)
            media={'path':str(fixture),'pause':False,'video-params':dict(w=160,h=120),'current-vo':'libmpv'}
            time_calls={71:0}
            def prop(path,key,pid,uid):
                if key!='time-pos':return media[key]
                time_calls[pid]+=1
                return 0 if time_calls[pid]==1 else .2
            endpoints=[socket.socket(socket.AF_UNIX)]
            endpoints[0].bind(str(root/'visual-reference-ipc.sock'))
            try:
                with patch.object(N,'mpv_property',side_effect=prop),patch.object(N.time,'sleep') as sleep:
                    with self.assertRaisesRegex(RuntimeError,'actual static visual fixture content unmatched'):
                        smoke.visual_media()
                self.assertEqual(sleep.call_args_list,[unittest.mock.call(.5)])
                smoke.controlled_controls_trials.assert_not_called()
                smoke.controlled_renderer_trials.assert_not_called()
                actual=json.loads((root/'visual-oracle.json').read_bytes())
                self.assertEqual(actual['oracle']['status'],'unmatched')
                self.assertEqual((actual['player_attempt_limit'],actual['capture_attempt_limit']),(1,1))
                self.assertEqual(len(actual['player_attempts']),1)
                smoke.native_protocol_diagnostic.assert_called_once()
                self.assertEqual(smoke.player_fullscreen.call_args_list[-1].args,(smoke.owned[0],False))
            finally:
                for endpoint in endpoints:endpoint.close()

    def test_first_failure_still_attempts_second_fixed_error_and_duplicate_player_unknown(self):
        for failure in ('exception','reused-player'):
            with tempfile.TemporaryDirectory() as temporary:
                first=Mock(owned=[],launches=[],observe=Mock(return_value=dict(player=dict(pid=20,start_ticks=2),status='observed')))
                second=Mock(owned=[],launches=[],observe=Mock(return_value=dict(player=dict(pid=20,start_ticks=2),status='observed')))
                if failure=='exception':first.observe.side_effect=RuntimeError('private unknown error')
                value,_=self.study(Path(temporary),[first,second])
                second.observe.assert_called_once();self.assertNotIn('private unknown',json.dumps(value))
                row=value['trials'][0 if failure=='exception' else 1]
                self.assertEqual(row['status'],'unknown');self.assertEqual(row['error'],'guard-error')

    def test_unretired_first_owned_player_prevents_second_arm(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);fixture=root/'fixture';fixture.write_bytes(b'fixed');expected=root/'expected';expected.write_bytes(b'fixed')
            smoke=N.Smoke.__new__(N.Smoke);smoke.root=root;smoke.uid=os.getuid();smoke.stage='live'
            primary_player=dict(executable='/usr/bin/celluloid',pid=11,start_ticks=1)
            smoke.owned=[primary_player];smoke.launches=[];smoke.finish_native_protocol=Mock()
            trial_player=dict(executable='/usr/bin/celluloid',pid=20,start_ticks=2)
            first=Mock(owned=[trial_player],launches=[],observe=Mock(return_value=dict(status='observed')))
            second=Mock(owned=[],launches=[],observe=Mock())
            primary=dict(oracle=dict(status='unmatched'),screenshot=dict(sha256='a'*64),capture_precondition={},
                fixture_sha256=N.digest(fixture),expected_rgb_sha256=N.digest(expected))
            def retire(player,uid):
                if player is trial_player:raise RuntimeError('private optional cleanup')
            with patch.object(N,'ControlsTrialSmoke',side_effect=[first,second]) as constructor,patch.object(N,'retire_renderer_player',side_effect=retire):
                smoke.controlled_controls_trials(fixture,expected,'b'*64,primary)
            second.observe.assert_not_called();self.assertEqual(constructor.call_count,1)
            value=json.loads((root/'0-controls-state-trials.json').read_bytes())
            self.assertFalse(value['trials'][0]['owned_trial_cleanup_completed'])
            self.assertEqual(value['trials'][1]['status'],'unrun');self.assertEqual(value['preparation_error'],'guard-error')
            self.assertNotIn('private optional',json.dumps(value));self.assertTrue(value['primary_failure_preserved'])

    def test_new_receipt_cannot_follow_symlink_overwrite_or_exceed_old_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);sentinel=root/'foreign';sentinel.write_bytes(b'unchanged')
            path=root/'0-controls-state-trials.json';path.symlink_to(sentinel)
            with self.assertRaises(OSError):N.write_controls_receipt(root,os.getuid(),{})
            self.assertEqual(sentinel.read_bytes(),b'unchanged');path.unlink()
            N.write_controls_receipt(root,os.getuid(),dict(release_acceptance=False));before=path.read_bytes()
            with self.assertRaises(OSError):N.write_controls_receipt(root,os.getuid(),{})
            self.assertEqual(path.read_bytes(),before)
            with self.assertRaises(RuntimeError):N.write_controls_receipt(root,os.getuid(),{'test':'x'*(512*1024)})

    def test_finite_public_inventory_swaps_controls_without_retry_screenshot(self):
        spec=importlib.util.spec_from_file_location('controls_inventory_guest',HERE/'guest-check-native-v6.py')
        guest=importlib.util.module_from_spec(spec);spec.loader.exec_module(guest)
        new=guest.NATIVE_PUBLIC_EVIDENCE_FILES
        old=restore_controls_guest((HERE/'guest-check-native-v6.py').read_text())
        env={};exec(compile(old,'strict-rolled-back-source','exec'),env)
        removed={'0-controlled-renderer-trials.json','renderer-trial-default/reference.png','renderer-trial-gl/reference.png'}
        added={'0-controls-state-trials.json','controls-trial-transition/reference.png','controls-trial-hidden/reference.png'}
        current_labels={'failure-fresh-defaults-and-isolation','failure-archive-content-roundtrips',
            'failure-actual-role-file-manager-terminal-editor','failure-open-codec-content-and-player-state',
            'failure-portal-and-accessibility-reachability','failure-owned-process-cleanup-config-preservation',
            'failure-selinux-and-new-avcs','text-fixture-before-location','text-fixture-navigation-confirmed',
            'archive-fixture-before-location','archive-fixture-navigation-confirmed','media-fixture-before-location',
            'media-fixture-navigation-confirmed','file-manager-F4-mapped','editor-save-confirmed'}
        historical_labels=current_labels-{'media-fixture-before-location','media-fixture-navigation-confirmed'}
        added|={'gui-%02d-%s.png'%(index,label) for index in range(15) for label in current_labels}
        added-={'gui-%02d-%s.png'%(index,label) for index in range(13) for label in historical_labels}
        self.assertEqual(set(new)-set(env['NATIVE_PUBLIC_EVIDENCE_FILES']),added)
        self.assertEqual(set(env['NATIVE_PUBLIC_EVIDENCE_FILES'])-set(new),removed)
        self.assertEqual(len(new),len(env['NATIVE_PUBLIC_EVIDENCE_FILES'])+len(added)-len(removed))
        for name in added:self.assertTrue(guest.native_public_evidence_member(name))
        for name in removed|{'controls-trial-private/reference.png','controls-trial-transition/private.png'}:
            with self.assertRaises(RuntimeError):guest.native_public_evidence_member(name)

    def test_actual_emitted_guest_begin_matches_consumer_and_stale_identities_reject(self):
        guest_path=HERE/'guest-check-native-v6.py';raw=guest_path.read_text()
        spec=importlib.util.spec_from_file_location('controls_guest_begin',guest_path)
        guest=importlib.util.module_from_spec(spec);spec.loader.exec_module(guest)
        main=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='main')
        first_try=next(i for i,n in enumerate(main.body) if isinstance(n,ast.Try))
        prefix=ast.Module(body=main.body[:first_try],type_ignores=[])
        output=io.StringIO()
        with patch('sys.argv',['labelled-source-fixture','live']),contextlib.redirect_stdout(output):
            exec(compile(ast.fix_missing_locations(prefix),str(guest_path),'exec'),guest.__dict__)
        begin=output.getvalue().strip()
        spec=importlib.util.spec_from_file_location('controls_consumer',HERE/'evidence.py')
        evidence=importlib.util.module_from_spec(spec);spec.loader.exec_module(evidence)
        end='ARCTIC-NATIVE-RUNNER-END '+json.dumps(dict(stage='live',status='failed',error='source fixture',evidence_export_complete=False,release_acceptance=False))
        _,identity,terminal=evidence.native_block(begin+'\n'+end+'\n','live')
        self.assertEqual(identity['native_source_sha256'],hashlib.sha256((HERE/'native_smoke.py').read_bytes()).hexdigest())
        self.assertEqual(identity['checker_sha256'],hashlib.sha256(guest_path.read_bytes()).hexdigest())
        self.assertEqual(terminal['status'],'failed')
        for field,old in (('native_source_sha256',BASE_NATIVE_SHA),('checker_sha256',BASE_GUEST_SHA)):
            stale=dict(identity,**{field:old})
            with self.assertRaises(RuntimeError):evidence.native_block('ARCTIC-NATIVE-RUNNER-BEGIN '+json.dumps(stale)+'\n'+end+'\n','live')


if __name__=='__main__':unittest.main()
