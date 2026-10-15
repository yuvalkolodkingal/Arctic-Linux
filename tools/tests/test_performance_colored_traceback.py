"""Exact upstream colors yield closed unauthenticated source IDs only."""
import copy
import hashlib
import json
import re
import shutil
import types
import unittest
from unittest.mock import patch
import test_performance_failure_phase as P


class ColoredTracebackTest(unittest.TestCase):
    def setUp(self):
        self.fixture = P.FixedFailurePhaseTest('runTest')
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        self.fixture.prepare_guest()
        self.original = (P.ROOT/'tools/performance/run-paired.py').read_bytes()
        raw = self.original
        for feature in (b'performance-prescreen-only', b'performance-prescreen-main-only',
                        b'performance-prescreen-stage-only'):
            raw = re.sub(rb'(?ms)^[ ]*# ' + feature + rb'-begin\n.*?^[ ]*# ' + feature + rb'-end\n', b'', raw)
        raw = b''.join(line for line in raw.splitlines(keepends=True)
            if b'performance-prescreen-only' not in line)
        raw = raw.replace(b'\n\n\ndef main():\n', b'\n\ndef main():\n', 1)
        raw = raw.replace(b'        print(phase, flush=True)\n\n\n    def require_idle_vm_host():\n',
            b'        print(phase, flush=True)\n\n    def require_idle_vm_host():\n', 1)
        raw = raw.replace(b'                 planned_boot_order=[dict(image=name, boot=number) for number, name in paired_boot_order()])\n    def save(phase):\n',
            b'                 planned_boot_order=[dict(image=name, boot=number) for number, name in paired_boot_order()])\n\n    def save(phase):\n', 1)
        raw = re.sub(rb'(?ms)^[ ]*# colored-trace-only-begin\n.*?^[ ]*# colored-trace-only-end\n', b'', raw)
        raw = b''.join(line for line in raw.splitlines(keepends=True) if b'# colored-trace-only # envelope-only' not in line)
        raw = raw.replace(b"exception_class='none', format='none'),\n", b"exception_class='none', format='none')),\n", 1)
        # Preserve the original history digest through exact reviewed identity inverses.
        historical = raw
        historical = historical.replace(b'pinned 110-site inventory', b'pinned 104-site inventory')
        historical = historical.replace(b'Complete 110-site inventory bound to the frozen observer.',
                                        b'Complete 104-site inventory bound to the original frozen observer.')
        historical = historical.replace(b"len(inventory) != 110 or digest != '0036a44d0991027dabbdfd3a0e52dd42faaacbb3b1ce77f5dae096737c507b51'",
                                        b"len(inventory) != 104 or digest != '2d94f03b8519b3a3e4d95f24a2834dec5171997a84e6deba1f02e20fd936701b'")
        self.assertEqual(historical.count(b'not 942 <= frames[1][0] <= 1008'), 1)
        historical = historical.replace(b'not 942 <= frames[1][0] <= 1008',
                                        b'not 871 <= frames[1][0] <= 942')
        for current, previous in (
                (b'ae57b29c0d36b833ec571b2d8886e3468459db40551e2a127b906602e7401818', b'c6532d1b6dde6101c7f8856072498985b3be5aeb7d91d873ac428610e1dc7ae6'),
                (b'd751e1f6f52f574a3d247dfa09aa984ad791d2c3873d8193fa4eb9c6e8c2d02e', b'5a1bce24d3097cbeeb936701de0cf87b4bc8bf7f8aa121dc0f7a498b9a821b1e'),
                (b'1de5938ab1c96951dffcc84980d59f373124a26955a6ef292216973917d3aafd', b'dce568410fb95f027c1ab4b44148b8af93ea16f32e0b64dcff79bcb707b77940'),
                (b'96ccc1e7a992a092e79aa00661f0098acaeba8e3f3ef76ff856716b720ac3158', b'bdd1dbcc5f45af671063b58779306f8add7ccfd656549495937e91996ccbf562'),
                (b'c6532d1b6dde6101c7f8856072498985b3be5aeb7d91d873ac428610e1dc7ae6', b'7f0eb763b0b649a7b60153e3c11518029f71b44e08d6714f013db51409c6a2ed'),
                (b'5a1bce24d3097cbeeb936701de0cf87b4bc8bf7f8aa121dc0f7a498b9a821b1e', b'733870e07dfed54229b9b8bf21000573545fe2479c2fd9c35454be301c8683e7'),
                (b'69ab0810e5e4e521f238a2a4ad2bf262b50791c288fdf2d071b3ee72ebcd6e73', b'088eaa168c30e0ab4faae90e50045f6615f29594dc06a7361ee8ea398951636d'),
                (b'dce568410fb95f027c1ab4b44148b8af93ea16f32e0b64dcff79bcb707b77940', b'd3d3ac5dcdf9066b73ac91a48c968dd7f84cd43f3c5571939d7c1041f879a0cf'),
                (b'bdd1dbcc5f45af671063b58779306f8add7ccfd656549495937e91996ccbf562', b'3195ee9137ca9dbd908c9021336a1f262c298ef51725bc8b2a8619d26c54e4d9'),
                (b'7f0eb763b0b649a7b60153e3c11518029f71b44e08d6714f013db51409c6a2ed', b'19fb089b8885a1e0ce6b2827db9b87acade30bef3a331486ca05d0a051ddea8b'),
                (b'733870e07dfed54229b9b8bf21000573545fe2479c2fd9c35454be301c8683e7', b'c16a9947baa293502791af88f60e14bcd8dea0b852286536a75598afef371d1b'),
                (b'088eaa168c30e0ab4faae90e50045f6615f29594dc06a7361ee8ea398951636d', b'4892222d52beb2c2007a457f43b4f0389e81b279222e22aa923d49fa6ff1b0d5'),
                (b'19fb089b8885a1e0ce6b2827db9b87acade30bef3a331486ca05d0a051ddea8b', b'515ff75b394b28c9d2d02f0838612cbb86b06e2a24be25580f19554632abe064'),
                (b'c16a9947baa293502791af88f60e14bcd8dea0b852286536a75598afef371d1b', b'9acbe74ffb8c64b63f9f180246c26ba69ae2ba80c620a1cb8baca8d9fdc4fc79'),
                (b'd3d3ac5dcdf9066b73ac91a48c968dd7f84cd43f3c5571939d7c1041f879a0cf', b'4d1fffe1fa047ea23d1902de4b2cd0e5f6fdf6bc5143c61b1e57aa7b2ae687b9'),
                (b'4892222d52beb2c2007a457f43b4f0389e81b279222e22aa923d49fa6ff1b0d5', b'5f3228d6f09a97e7640f522663bbfa32632f63387a3b59235caa3caab64bf92e'),
                (b'515ff75b394b28c9d2d02f0838612cbb86b06e2a24be25580f19554632abe064', b'1940fc7495315aa6ceff7b5fbff9554b081182404733f1443e2fee5bc8c5c8a2'),
                (b'9acbe74ffb8c64b63f9f180246c26ba69ae2ba80c620a1cb8baca8d9fdc4fc79', b'7b7890ffdd227ae465ed856440e9bd03a36185a90cadbcb2926ad0eae2204bb7'),
        ):
            self.assertEqual(historical.count(current), 1)
            historical = historical.replace(current, previous)
        self.assertEqual(hashlib.sha256(historical).hexdigest(), '6ed895e00eb9f80a964aa50066bb244a3a390aa696c31bbde652301b7638f799')
        self.old = types.ModuleType('original_color_classifier'); self.old.__file__ = str(P.ROOT/'tools/performance/run-paired.py')
        exec(compile(raw, self.old.__file__, 'exec'), self.old.__dict__); self.old.ROOT = P.inner.ROOT
        consumer = (P.ROOT/'tools/performance/qualification.py').read_bytes()
        consumer = P.before_epiphany_failure_sites(consumer)
        consumer = re.sub(rb'(?ms)^[ ]*# colored-trace-only-begin\n.*?^[ ]*# colored-trace-only-end\n', b'', consumer)
        consumer = consumer.replace(b", 'colored_traceback'}", b"}", 1)
        self.assertEqual(hashlib.sha256(consumer).hexdigest(), 'e452f27cc1229684613f39dc2ff59d6b32500b817cf97f26cc74f80434943495')

    def result(self, trace):
        uart = self.fixture.work/'runs/baseline/1/serial-boot.log'
        uart.write_bytes(trace.encode() if type(trace) is str else trace)
        result = self.fixture.summary(); old = self.old.failure_phase_summary(self.fixture.work, 'sensitive_text')
        without = copy.deepcopy(result); without['guest_envelope'].pop('colored_traceback')
        self.assertEqual(without, old)
        raw = json.dumps(result).encode(); self.assertEqual(P.screen.external_text(raw), raw)
        for private in (b'guest-check.py', b'do-not-export', b'private.invalid', 'מילים סודיות'.encode()): self.assertNotIn(private, raw)
        self.assertFalse(result['release_acceptance']); self.assertFalse(result['performance_acceptance'])
        return result

    def colored(self, site=None):
        trace = self.fixture.guest_trace(site)
        trace = re.sub(r'  File "([^"]*)", line ([0-9]+), in ([^\n]+)',
            lambda m:'  File \x1b[35m"'+m[1]+'"\x1b[0m, line \x1b[35m'+m[2]+'\x1b[0m, in \x1b[35m'+m[3]+'\x1b[0m', trace)
        return re.sub(r'(?m)^(RuntimeError|ValueError|InterruptedError): ([^\n]*)$',
            lambda m:'\x1b[1;35m'+m[1]+'\x1b[0m: \x1b[35m'+m[2]+'\x1b[0m', trace)

    def consumer(self, result):
        target = self.fixture.root/'screened'
        if target.exists(): shutil.rmtree(target)
        with patch.object(P.inner, 'failure_phase_summary', return_value=result): self.fixture.export(target)

    def test_all_110_source_color_projections_leave_original_unknown(self):
        for site in self.fixture.sites:
            with self.subTest(source=site['source'], line=site['line']):
                result = self.result(self.colored(site)); projection = result['guest_envelope']['colored_traceback']
                self.assertEqual(result['guest_failure']['status'], 'unknown')
                self.assertEqual(projection, dict(reason='source_projection', code=site['source']+'_'+str(site['line']),
                    exception_class=site['exception'], frames='multiple', candidates='one', format='python314_default'))
                self.consumer(result)
                self.assertLessEqual((self.fixture.root/'screened/unqualified-failure-phase.json').stat().st_size, 4096)

    def test_plain_all_110_existing_source_admission_unchanged(self):
        for site in self.fixture.sites:
            result=self.result(self.fixture.guest_trace(site))
            self.assertEqual(result['guest_failure']['status'],'source_known_shape')
            self.assertEqual(result['guest_envelope']['colored_traceback']['code'],'none')

    def test_custom_malformed_colors_headers_paths_frames_and_message_are_closed(self):
        valid=self.colored()
        for fault in (valid.replace('[35m"','[31m"'), valid.replace('/run/t/guest-check.py','/run/t/private.py'),
                valid.replace('/run/t/guest-check.py','/run/t/guest-check.py/..'), valid.replace('line \x1b[35m362','line \x1b[35m0362'),
                valid.replace('in \x1b[35mdesktop','in \x1b[35mprivate_function'),
                valid.replace('Traceback (most recent call last):','\x1b[35mTraceback (most recent call last):\x1b[0m'),
                valid.replace('No unique non-root Mango session','private forged message'),
                valid.replace('\x1b[1;35mRuntimeError','\x1b[1;31mRuntimeError'), valid.replace('\x1b[35m362\x1b[0m','\x1b[35m362'),
                valid.replace('in \x1b[35mmain\x1b[0m','in \x1b[35mprivate\x1b[0m')):
            result=self.result(fault); self.assertEqual(result['guest_envelope']['colored_traceback']['code'],'none')

    def test_unknown_untrusted_code_context_rejected_and_exact_source_context_admitted(self):
        site=next(x for x in self.fixture.sites if (x['source'],x['line'])==('guest',362))
        valid=self.colored(site); boundary='\n\x1b[1;35mRuntimeError'
        source=(P.ROOT/'tools/performance/guest.py').read_text().splitlines()[361].strip()
        wrapper = valid.replace('in \x1b[35m<module>\x1b[0m\n',
            'in \x1b[35m<module>\x1b[0m\n    measurement["main"](preconditioned=True, causal_precision=True)\n')
        self.assertEqual(self.result(wrapper)['guest_envelope']['colored_traceback']['code'], 'guest_362')
        for context in ('    '+source+'\n','    \x1b[1;31m'+source+'\x1b[0m\n    \x1b[1;31m^^^^\x1b[0m\n'):
            result=self.result(valid.replace(boundary,'\n'+context+'\x1b[1;35mRuntimeError'))
            self.assertEqual(result['guest_envelope']['colored_traceback']['code'],'guest_362')
        for context in ('    private forged source\n','    \x1b[32m'+source+'\x1b[0m\n','    \x1b[1;31mprivate\x1b[0m\n','    '+source+'\x07\n'):
            result=self.result(valid.replace(boundary,'\n'+context+'\x1b[1;35mRuntimeError'))
            self.assertEqual(result['guest_envelope']['colored_traceback']['code'],'none')

    def test_ambiguous_tracebacks_exception_identity_and_private_uart_remain_closed(self):
        valid=self.colored()
        record=self.fixture.guest_record('observer_source_sha256',self.fixture.observer['source_sha256'])
        for trace in (valid.replace('Traceback (most recent call last):','Traceback (most recent call last):\nTraceback (most recent call last):'),
                valid.replace(record,record+record), valid.replace(record,''), valid.replace(self.fixture.observer['source_sha256'],'a'*64),
                valid.replace('ARCTIC-COLLECT-END','PRIVATE-COLLECT-END'), valid[:-1], valid.encode()+b'\xff\n',valid+'\x00\n',
                valid.replace('\nARCTIC-INSTALLED-SMOKE-EXIT=','\n\x1b[1;35mRuntimeError\x1b[0m: \x1b[35mprivate\x1b[0m\nARCTIC-INSTALLED-SMOKE-EXIT=')):
            self.assertEqual(self.result(trace)['guest_envelope']['colored_traceback']['code'],'none')

    def test_source_mutation_and_wrong_uart_owner_cannot_project(self):
        valid=self.colored(); self.result(valid)
        source=P.inner.ROOT/'tools/performance/guest.py'; original=source.read_bytes()
        source.write_bytes(original+b'\n# mutation\n')
        try:self.assertEqual(self.result(valid)['guest_envelope']['colored_traceback']['reason'],'not_observed')
        finally:source.write_bytes(original)
        real=P.inner.os.fstat
        def wrong(fd):
            info=real(fd); fields=list(info); fields[4]=P.os.geteuid()+1
            return P.os.stat_result(fields)
        with patch.object(P.inner.os,'fstat',side_effect=wrong):
            self.assertEqual(self.result(valid)['guest_envelope']['colored_traceback']['reason'],'not_observed')

    def test_consumer_rejects_open_codes_arbitrary_fields_and_inconsistent_prerequisites(self):
        original=self.result(self.colored());self.consumer(original)
        for fault in ('code','class','format','frames','candidates','extra','owner','observer','shape','type'):
            result=copy.deepcopy(original);out=result['guest_envelope']['colored_traceback']
            if fault=='code':out['code']='guest_361'
            elif fault=='class':out['exception_class']='PrivateError'
            elif fault=='format':out['format']='ansi_stripped'
            elif fault=='frames':out['frames']='one'
            elif fault=='candidates':out['candidates']='multiple'
            elif fault=='extra':out['path']='private'
            elif fault=='owner':result['private_owner_verified']=False
            elif fault=='observer':result['guest_envelope']['counts']['admitted_observer_records']='zero'
            elif fault=='shape':result['guest_envelope']['exception_shape']['format']='plain'
            else:out['code']=True
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.consumer(result)

if __name__=='__main__':unittest.main()
