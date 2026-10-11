#!/usr/bin/env python3
"""Fresh admission around exact original UI host and accepted retained evidence."""
import argparse,hashlib,os,stat,sys
from pathlib import Path
import common as C
HERE=Path(__file__).resolve().parent

def originals_module(value):
    path=C.ROOT/C.COMPONENT_PREFIX/'originals.py'
    return C.load(path,'ui_retained_original_primitives',value['execution_files'][C.COMPONENT_PREFIX+'originals.py'])

def component_module(value,originals):
    old=sys.modules.get('originals');absent='originals'not in sys.modules
    try:
        sys.modules['originals']=originals
        path=C.ROOT/C.COMPONENT_PREFIX/'observer.py'
        return C.load(path,'ui_retained_accepted_observer',value['execution_files'][C.COMPONENT_PREFIX+'observer.py'])
    finally:
        if absent:sys.modules.pop('originals',None)
        else:sys.modules['originals']=old

def main_adapter(value):
    C.manifest(value)
    buffers={}
    for path,expected in value['execution_files'].items():
        raw=C.regular(C.ROOT/path,1024*1024)
        C.require(hashlib.sha256(raw).hexdigest()==expected,'Fresh UI whole Source buffer differs');buffers[path]=raw
    originals=originals_module(value);helper=component_module(value,originals)
    declared=C.strict_json(buffers[C.COMPONENT_PREFIX+'execution-manifest.json'])
    (_,unused_state),published=helper.build(declared,C.ROOT)
    original_manifest=C.strict_json(buffers[C.ORIGINAL_PREFIX+'execution-manifest.json'])
    def admitted_guard(supplied,source,inputs=None):
        C.require(type(supplied)is dict and supplied==original_manifest,'Original UI manifest projection differs')
        return C.guard(value,source,inputs)
    observed,state=helper.bind(published,buffers[C.ORIGINAL_PREFIX+'run.py'],buffers[C.ORIGINAL_PREFIX+'common.py'],
        buffers['tools/native-functional/screen-evidence.py'],buffers[C.COMPONENT_PREFIX+'match-diagnostic.py'],
        C.ROOT/C.COMPONENT_PREFIX/'match-diagnostic.py',buffers['tools/test-install.sh'],admitted_guard)
    C.require(observed.main.__code__ is published.main.__code__ and observed.C.decode is published.C.decode,
        'Original UI main/decode Code differs')
    return observed,published,state,helper,originals,buffers

def publication_output(output,originals):
    # Exact accepted publication_output body, with only explicit primitive aliases.
    require=originals.require;owned_fd=originals.owned_fd;same=originals.same
    output=Path(output);require(output.is_absolute() and output.resolve()==output)
    before=output.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_uid==os.geteuid()
            and before.st_nlink==1 and not before.st_mode&0o022 and before.st_size==0)
    raw=b'upload_admitted=true\n'
    with owned_fd(output,os.O_WRONLY|os.O_APPEND|os.O_NOFOLLOW|os.O_NONBLOCK) as fd:
        require(same(before,os.fstat(fd)));at=0
        while at<len(raw):
            count=os.write(fd,memoryview(raw)[at:]);require(type(count) is int and count>0);at+=count
        final=os.fstat(fd)
        require(final.st_size==len(raw) and same(final,output.lstat()))

def main():
    value=C.manifest(C.strict_json(C.regular(HERE/'execution-manifest.json',1024*1024)),True)
    observed,published,state,helper,originals,buffers=main_adapter(value)
    if '--screen'in sys.argv[1:]:
        parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--screen',action='store_true')
        for name in('source','inputs','out'):parser.add_argument('--'+name,type=Path,required=True)
        args=parser.parse_args();source=args.source.absolute();target=args.out.absolute()
        scanner=C.load(C.ROOT/'tools/native-functional/screen-evidence.py','ui_retained_publication_scanner',
            value['execution_files']['tools/native-functional/screen-evidence.py'])
        callback=lambda:publication_output(Path(os.environ['GITHUB_OUTPUT']),originals)
        helper.screen(published.screen,source/'public',target,source/'private/ui-evidence-snapshot',
            published.C,buffers[C.ORIGINAL_PREFIX+'common.py'],scanner,buffers['tools/native-functional/screen-evidence.py'],
            buffers[C.COMPONENT_PREFIX+'match-diagnostic.py'],on_ready=callback)
        return 0
    return observed.main()

if __name__=='__main__':
    try:raise SystemExit(main())
    except (KeyboardInterrupt,SystemExit):raise
    except BaseException:
        # Exceptions preserve their identity inside the adapter; the public
        # command emits no operand, traceback, unknown path or private message.
        print('ARCTIC-UI-RETAINED-EVIDENCE=failed-closed',flush=True)
        raise SystemExit(1)
