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
        raw = re.sub(rb'(?ms)^[ ]*# colored-trace-only-begin\n.*?^[ ]*# colored-trace-only-end\n', b'', self.original)
        raw = b''.join(line for line in raw.splitlines(keepends=True) if b'# colored-trace-only # envelope-only' not in line)
        raw = raw.replace(b"exception_class='none', format='none'),\n", b"exception_class='none', format='none')),\n", 1)
        # Preserve the original history digest through exactly three reviewed identity inverses.
        historical = raw
        for current, previous in (
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

    def test_all_104_source_color_projections_leave_original_unknown(self):
        for site in self.fixture.sites:
            with self.subTest(source=site['source'], line=site['line']):
                result = self.result(self.colored(site)); projection = result['guest_envelope']['colored_traceback']
                self.assertEqual(result['guest_failure']['status'], 'unknown')
                self.assertEqual(projection, dict(reason='source_projection', code=site['source']+'_'+str(site['line']),
                    exception_class=site['exception'], frames='multiple', candidates='one', format='python314_default'))
                self.consumer(result)
                self.assertLessEqual((self.fixture.root/'screened/unqualified-failure-phase.json').stat().st_size, 4096)

    def test_plain_all_104_existing_source_admission_unchanged(self):
        for site in self.fixture.sites:
            result=self.result(self.fixture.guest_trace(site))
            self.assertEqual(result['guest_failure']['status'],'source_known_shape')
            self.assertEqual(result['guest_envelope']['colored_traceback']['code'],'none')

    def test_custom_malformed_colors_headers_paths_frames_and_message_are_closed(self):
        valid=self.colored()
        for fault in (valid.replace('[35m"','[31m"'), valid.replace('/run/t/guest-check.py','/run/t/private.py'),
                valid.replace('/run/t/guest-check.py','/run/t/guest-check.py/..'), valid.replace('line \x1b[35m360','line \x1b[35m0360'),
                valid.replace('in \x1b[35mdesktop','in \x1b[35mprivate_function'),
                valid.replace('Traceback (most recent call last):','\x1b[35mTraceback (most recent call last):\x1b[0m'),
                valid.replace('No unique non-root Mango session','private forged message'),
                valid.replace('\x1b[1;35mRuntimeError','\x1b[1;31mRuntimeError'), valid.replace('\x1b[35m360\x1b[0m','\x1b[35m360'),
                valid.replace('in \x1b[35mmain\x1b[0m','in \x1b[35mprivate\x1b[0m')):
            result=self.result(fault); self.assertEqual(result['guest_envelope']['colored_traceback']['code'],'none')

    def test_unknown_untrusted_code_context_rejected_and_exact_source_context_admitted(self):
        site=next(x for x in self.fixture.sites if (x['source'],x['line'])==('guest',360))
        valid=self.colored(site); boundary='\n\x1b[1;35mRuntimeError'
        source=(P.ROOT/'tools/performance/guest.py').read_text().splitlines()[359].strip()
        wrapper = valid.replace('in \x1b[35m<module>\x1b[0m\n',
            'in \x1b[35m<module>\x1b[0m\n    measurement["main"](preconditioned=True, causal_precision=True)\n')
        self.assertEqual(self.result(wrapper)['guest_envelope']['colored_traceback']['code'], 'guest_360')
        for context in ('    '+source+'\n','    \x1b[1;31m'+source+'\x1b[0m\n    \x1b[1;31m^^^^\x1b[0m\n'):
            result=self.result(valid.replace(boundary,'\n'+context+'\x1b[1;35mRuntimeError'))
            self.assertEqual(result['guest_envelope']['colored_traceback']['code'],'guest_360')
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
