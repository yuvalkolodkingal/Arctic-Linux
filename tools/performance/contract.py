#!/usr/bin/env python3
"""Replay a separately frozen paired lane without changing its numeric gates."""
import hashlib
import json
from pathlib import Path
import re
import tempfile

MODE = 'frozen-external-paired-v1'
WORKFLOW = '.github/workflows/paired-candidate-20261009.yml'
MARKER = '.github/qualification-20261010.performance'
MANIFEST = 'tools/performance/execution-manifest.json'
ARTIFACT = 'external-paired-performance'
BRANCH = 'codex/qualification-dispatch-20261010'
BASELINE = dict(name='Arctic-Linux-1.2-x86_64.iso', bytes=2322073600,
    sha256='054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f',
    profile_sha256='e6b9aa317521bdaaaf343629bc5de8b914b0a5f58387a0c9fe31754f17c0d20d')
CANDIDATE_SOURCE_FILES = frozenset(('profiles/ci/offline.toml', 'shell/AppsService.qml', 'shell/BatteryService.qml'))
EXECUTION_FILES = frozenset((WORKFLOW, 'tools/performance/qualification.py',
    'tools/performance/contract.py', 'tools/performance/compose-plan.py',
    'tools/performance/run-paired.py', 'tools/performance/compare.py',
    'tools/performance/compose-paired-probe.py', 'tools/performance/guest.py',
    'tools/performance/causal.py', 'tools/performance/prepare-vm-tools.sh',
    'tools/performance/fixtures/v1.2-offline.toml', 'tools/performance/producer-receipt.py',
    'tools/test-install.sh', 'tools/lib/container.sh', 'tools/lib/vmtest.py',
    'tools/native-functional/fetch-image.py', 'tools/native-functional/screen-evidence.py'))
ORDER = (('baseline', 1), ('candidate', 1), ('candidate', 2),
         ('baseline', 2), ('baseline', 3), ('candidate', 3))


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def same(left, right):
    """JSON equality which never equates a boolean with a numeric gate input."""
    return json.dumps(left, sort_keys=True, separators=(',', ':'), allow_nan=False) == json.dumps(
        right, sort_keys=True, separators=(',', ':'), allow_nan=False)


FAILURE_OBSERVATION_HELPER = '''import builtins,json,sys,types
def install(roots,store,source):
 old=sys.excepthook
 names="RuntimeError TypeError NameError ValueError AttributeError KeyError IndexError AssertionError OSError FileNotFoundError PermissionError TimeoutError ProcessLookupError InterruptedError EOFError ZeroDivisionError OverflowError MemoryError KeyboardInterrupt".split()
 classes=tuple((getattr(builtins,n),n) for n in names)+((store,"StoreProofError"),)
 def hook(kind,error,original):
  try:
   label=next((n for c,n in classes if type(error) is c and kind is c),"unsupported")
   domain,site,phase,relation="none","none","unavailable","none"
   tb=original;count=0;selected=0
   while type(tb) is types.TracebackType and count<128:
    count+=1
    for tag,root in roots:
     pending=[root]
     while pending:
      code=pending.pop()
      if tb.tb_frame.f_code is code and any(a<=tb.tb_lasti<b and line==tb.tb_lineno for a,b,line in code.co_lines()):
       domain,site,phase,selected=tag,tag+"_"+str(tb.tb_lineno),code.co_name,count
      pending.extend(c for c in code.co_consts if type(c) is types.CodeType)
    tb=tb.tb_next
   if tb is not None:domain,site,phase,selected="none","none","unavailable",0
   relation=("leaf" if selected==count else "ancestor") if selected else "none"
   record={"schema":"arctic-loaded-failure-observation-v1","exception_class":label,"domain":domain,"site":site,"phase":phase,"relation":relation,"source_sha256":source}
   print("ARCTIC-PERFORMANCE "+json.dumps({"stage":"installed","check":"failure_observation","value":record},sort_keys=True,separators=(",",":")),flush=True)
  except BaseException:pass
  old(kind,error,original)
 sys.excepthook=hook
'''

SOURCE_TRANSPORT_HELPER = '''import base64,hashlib,zlib
def unpack(value,size,sha):
 if type(value) is not str or len(value)>131072 or type(size) is not int or not 0<size<=131072 or type(sha) is not str or len(sha)!=64:raise ValueError("Observer transport bounds differ")
 packed=base64.b64decode(value,validate=True)
 decoder=zlib.decompressobj();raw=decoder.decompress(packed,size+1)
 if len(raw)!=size or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail or hashlib.sha256(raw).hexdigest()!=sha:raise ValueError("Observer transport identity differs")
 return raw.decode("utf-8")
'''

# Deliberately regenerate this reviewed literal when Causal Source bytes change.
CAUSAL_TRANSPORT = ('d6af122d05390f96bf020f728ec9d74066f8d5b5e91d2f9b0cbb0bb187c508ec', 74354,
    'eNrtffub27ax6O/7VzDOSSh5JZnUW5soPY69afbW9rq2k7Z3reqj+NhVrVdFybuuvedvv/MAQIAE9bCTc8/5vqa1LZLAABgM'
    'BoPBPB48ePAqDqL6cjH74ITBNg1mzjxYraaLa2ey3C6itObQt+nC2dzETjRNV8s0mMxiZx4H6XYdz+PFxrnexummcXLyBorc'
    'ztbL5SZ1boJFBMXW8Wa7XjirdZzG6/dx6kwjqDHdfIBXy/fxIliEccN5vI2mmziCZtLNehtupstFejKdz+NoGmxiaH8SJ8t1'
    '7ABMJ0g28dp5Hiyul24KvV0E11AznE0Bbn02TTcIJV4jDGeyDsJ38eZkcxNsnDSYx85mHSzSKX6EVmczZ5vGNLJ38XoRz5x1'
    'cAugluG775zFchE709QJnGRNNadzGGUwX50s19AR5+LlExgd4ANaq0fxbPo+Xn/ISjWcl+vlBPCxXL+DcvMAeiXRqOEubZy8'
    'WDrhcg54nW4AcriM4hr8vUim19t1gD2tOWl4E0fbGU4LFHl9/my62N45abzZ4CvoZAjoBjQ0Th48eACIWy3XG5iB9GY2nZwk'
    '6+UcAW7iuw08O+KzeMMIXMtKy5TLr4LNjVb4JTzKIutY/krjWRxu1NP0ehHM1BNNpHraTmC+wzhN5ZvNzRooD7qvXgDm5O/t'
    'dhqdnLz+2/MfL585Q8cFohpDX8dIBNDKeLNczeL38WzMVDZ+749DALeJ3ZOLp+cv3lz8dHH+anz500+vz99A/U7Xcb527vrd'
    'cbetCNRrND1ntZ3MpqFzA12J1zXqVOysllNAzTp1Tp3N7RIqjJGs0pOfzx8/BbCvf37cBIjQrUGz05r4QehPun3P98NJy2uH'
    'XjiY9NtBt9vr93qDIAz7TW8waPstP2j5id/zomZ30O5EXtJyT15f/vLqybkGstPpe1F70g37XiuZtDrt/mQS+1476Uy8STRJ'
    'ok7g9ybtZhT5vVar0w+CTrMbBl48gN9ev++ePD9/8/PlU4E1HGkdR1oHRNXnuGjqYsnQWqkv19PrKUxbHVd9VId1yqunLpZO'
    'HVZE/X0HwD7+6/j8V8DtawDd9wfNk8cvX148zZDc7p/8/PjF02fn46eP3zzO3vc9qPvij5fj4lj73W4TsNTv9PpBs9PudDud'
    'qA0Ym/QGXtBr+X5zEvfiIOlO/CiYDCK/25y0/UEnGnSbcZy4AnBhXryw102iZtBMur0eYDyIBnHS7EXJoDnottttQGPih91B'
    'OGl7gdeJAvhf1PFjr+NFrXYTkHj56uKPFy8ePxvzIB//8vTijdZAK+zG/bjf6TebfifwmhO/G0/CZhtehf0w6HvQFkx01J2E'
    'fthqJZ1et99Oup1uAsTRHTTdk6+d87sg3DiB4HzzILyZAsPh5T9dhLMtLg4nJq6iT5nJ3hbhTQOBQXUniObTDQK7vVkC643v'
    '4nC7IWY9RdYTxat4gdwX+KlotuE8YcbhTLbTWeRcPE1rAE3vDDKcxz9ewKr/53aKLNhZxLcAewXrZrpBLp5MZ9Dl2+nmBngm'
    '7QUpAEyC2WwCJNSASQIcvvjj+OWry58unp0j/VROHPgvmoabStbLcXoDVNAdujA13V63l4Re1Pfb8cDzmi2vGw76rU6zPWn3'
    'unEUdnt+FHfa7aQ1aQbdpNfpxEEP1kIUTny3RuDpvwVw0PfxmMarGoiCcOJFuGTi3iQA+INB0PMmzbjbTdqDXqc7gPmMWlG7'
    'mbRjIJ+w2+x7SQ/XZdDp+aHeQLJd0H41RjSMl0kCXHno3bVbXuTVsq/p9F/xsO17A1tV1a92v+vDqvAnfVhh0aATt7xkMkl6'
    '7WjS7sbNdtKPW1Gv1Y+bXh+ozYs7A1w8g17T89pBU++XtpUWutahLYZ2TGKr4hM03dYgzJa38XpcAicd0uxtgulMgBzUiI3S'
    'E7Am3LTWy9ksXtObqNuq6r1bheMSzHUnHiDOKEDI85utdhkERTl+6PU8H1jGZOADI+4nwB2DZjcCftX1er1k0J5EbSjV67UG'
    '0aTndbuT7iTwejDTwGgiHYECP5sPq6xzCmuwfSdBqD60mv2acxddU2kolkGhl3K3EqU7XS5MLFchf9DUq90GH2bAshlgs5a9'
    'CGdBmqpK7bbAatlaaia+7/WATfmdXtLutf1+mERBvxdF3gA2pMmk78dhNOhFYRM2Jb/fjrwQdhdYF5MIWPLkf8ZagjEcu5Za'
    'A9pMetGkleAO3Uk82Hz7sGd2m03o4wT+mjSbHS8GBoLbddwLwtbAS5CFDCbhoWup6//ma6nrG2upV1hLwb/X0v+PtdRFAo+6'
    'EVCRHwPH85r9BLb/MIjaILLAAgNpbQDSXdSKAb/dZtLq92C7j5PAT3ogy/2v3Zd8P+h0ozZsySCOgfyUtLtJ0I1gWMBD+v04'
    'THwgjEnYCjvtuD3odnrNXht2KQ/kujawmn/vS/9eS7m1NEDhOQZRv+t7SdiHjjYjP+6CtNfrDLr9IAE+HMFW1fGbbVxwQXMS'
    'THr9CaCu2/fDYO9agvPBoN/0B20QtyetAI5QPmxrLQ8IMkjgpDZBGRIILvTgQDZIev02nK+CxPOjTjvqe//el/69L/1vWUsd'
    '2CBAxosGrQEcOtv90IOdym/3g+4AtouoE076naDV8dqJn/Q7HTj8JkECqJ70Ezgy9RO3Zl9C/Ulz0ux2JmHc7HU7YRK2W0HX'
    '63qdJIh7fhuOsvBv4oVRq9uBw3kf0J3023Gn3/NgAQd9t3b8yvk9Fsxnr5PfYXl89qr4vRbDF62B40j/KIqvnpycRHEi1dFj'
    'oWiooGKyekbrAZW1Q9JUNlCXOJ582MRppUrfpokzixcVKFJ1fnC67Ye+1+S/UKEBr6/OuiPnq6Ezcd/e9ZLzZz+9vfOa8Md3'
    'z9QSXQfTNHZebReomzxfr5frivuCVoqzXa3iNWo/JrFUjaSsMo8jB6B12y53hFWL0E+mocZ2sQrCd2NUslbc7/1u+vPPF3/+'
    '858vfqb/YD6wy3IIXPmqST3tNrHr4tWAXnW6n99ZVERL7ZNQjUK/Udcjep7G16Shhr5fWTt/gR2H/7jTNdm1zuh08bDTrWac'
    'Tu6F0P0F6sDXqHOqiOK+N6qOqGyBtUHLQond4Bc0n42b+C6aXsfpRsz1PNigfhz7yYCwIUEv2FxeAZXhLN0E6w0sU1hlSElc'
    '5cq1rU93VLMUwJruSMGDKSsyaJwoVbPw1R3hrFJHTqkfPyjCLSAQp7+Ajyuqe5ZBGBkYMlrP8Q93VD0zGsE7geliG6uX1/Fm'
    'AxxQ4Ek+5dBVxtIMlBXYWg5tekunekMZPizjL6AIEaKDOiuDuwNLFk5bwJRttclbLKlTd4B11S+eCrQ5xJ5gE0+SeO1mkztb'
    'BhGvMV5vRL3yN1CvWoaAJfH7yhs5w6Hj032YfOePnG8dv4AQowwwku+HTGz8PiM7fK9KncqfnZExSzgT1F9CmH84SuSlokQr'
    'aqQXSxofXrNpqmrkQdiEhiExa78jooo40smGPpfS58GI04dxLP5KSOoYLJIsky3bBoCouLsFHK12OkXiBeRnq8ReyTUHXsGt'
    'vkLNVGV3UWwipgc9EF8AGx9dlKRgL3FvWDBxpfTk3ts4YbD4wMDfB7NtXM1wwYRBbxEz1EKDHkE4qB6wji8WeB87izexdj3D'
    'FzD5uxeJzQKmTocOXtZUcq0bqEGiQBxQjSohob1nZLiDLjdiBQPl8Si/1xaydddVyBBNHbNw8wPn8c1ADkBzANguYDKl4KPf'
    '32soERt0A4g3XkQVEpsF4qqGuCYK5leHrYO/LN4tlrcLwtd8Mr3eLrcpWwUoZqNfY30Hgg9NphSA5NIQBgqiZWAYQu7UyVsA'
    'JNmzhuDRLIKoXWCSa6emBDLDtqcLKt9IV7PpBt8AFWQDS6bxjHgafuEylRewlGtOp5pnH1yWUNPFUfMzMBp8A31lyRi/uHeu'
    'ZAuikD/as8+LDR5mB2/ngNKY9mqO362aFCQgeiPRXbfuamStMQIAhHBE+eaIYOmD0ssCKctf+vtT6FCd93Gj/wLfBkFRsWE2'
    'kCH8qenAhtrvWnGfzP2nz38QRSAxpwz8lCHUNWg2Ik4PIWJDPtdapOWVElMPws0W+L7G24UhhSRzGx2nGR2Lkz0J/2Pga7Cg'
    'o7RyvV5uVzUNai27yWUewR1/8ODBn+J4RYcFtvbQN6OfLl69fuMEGyfG62dkWfV0FYfTZBqKdglY44Rg0YV3HaUg58lPf6RN'
    'NYqRgZCRC7a/TOAMNYX30FwaC06zWTpkOrRu8Jk05bmD8+J2jqscKHMa6RY0ZKxB4F9/SH91wgD2kLguLZAi59WPf330ym/C'
    'n3aDQD1eX29ZoIg3yDGuqfJmHaweQa14vqL+hUsCu46dBV7Ko0kLFEGENCSqTnhtzedQHJZR4kp7lWk0PPUqpx8Lxin38FLu'
    'qA8KWogHo/vKN5M73LSANLBjbrbSXJh+BVi3xfgSmFx8CAXO7uBAyOY1w0PgUXkdFDDneA1Vi0YhB3YQIcqjKKshAKmJW6xr'
    'Kilkfe5LeEOGV0NWnt1F10OA4OkdyKsqsH7uc07DgSU+ikbvAZGujZvc+X6xKZu6IwfNXM4fF8E8PnXH7uk7WBdnMPzV2Uda'
    'vPeP6Nv9+CN+uXc+Zmv5/sy7+8jAz+7utUnB/07VLLMWpohOTROkJnfbahbguJIPjAUluvCS8I0fFXXhS14S8PbtwoRCKgEY'
    'htxPlYzSgL/msFdSCRxhTYCG//OcyhL3gtEREz2cz0kdEuP5aC6pRkF0BayYbMTiaLhfPq5K1RYL3//tPf7oYnfZohIIiwXZ'
    'MzkBiG9+pc+JGtWeA8NIzYocJBtWjlFBh+ZA6Zj4dUU9QwenUbbb/IpfA9giQLaI17DHCMNMtICcB8zWYzhBh7S7QNtoqMfW'
    'R8vtBpl2GMMucnHZkPwYdmUSprEZiyjtgcQBn+Dv5sOHLV++nqY4RrRO1buKk62Jb2IqfgpmKYtSSMrIbBjFwiQRTjIZfYyB'
    'n+Tf+L5773xyPiq4xgTBshFnDVg/9IjL4URfQeI7zFOl/BCVLSUuKDqCrVfvJabwOKLGSxIMDWnHkNV2d1Vxtwu0AYUtNr1Z'
    'rjcInb8SS4FHr+Y04e9qnl9qNWFtr7WKySy4Tl2q5h9XU+zcsDRA4oL3rVII04XeVaAFeGrT/32hmFQ2y+YoZ8sFoXAsViEq'
    'N+C5T/8vtmT0Nl8X8DqerlwUkndUH49hbQTj2TKk4V6NEEQmZCCizJ4LKWx3v6ndsl5DvVaT8JPtDqKbbXt5aydzewX21BM9'
    'PRCCfZgHVs5a7ZdW3IK4ocaJFNOUKMk+skCEBOKV44uLkvyDJSVmhZL7PWJxSqc+XG283dMpaQwnOGBnuJjWcQMlWrzwyJae'
    'e+W83YweUtmzytXfv3u7GJ1Wv+O3Yr+vXHn1weijX+vcyy+uBgE1BLYyTBn4xR+petUTc4tex+FyTdxDsQjJ7s8MxUaBgWI9'
    'wT2l4odfsuanQOk42XCSGaOBuph7fBS6WHxBjD/7zo/i+31ev5HnWXJY7+IPNdho5lPa4yoV0Q6Rd6vfpoln0PjKa7aLmpNb'
    'miwcyhVAIxZNnRoZ5WxIwRsT2EWr+kakNN3fD0W/xEd42YDzbIr7XAWlqKr1ACuUR0j3iFgsSDtm9mLDLxCmC/+Ddugb/Ov+'
    'l0tIoWe6pLktbSQ3YnWT8ZXtwgY6jhqYihuk4XTqVg3Few6hpdNFqpMM1waBjAztSkHFRu8BpU7HEVoZPB4TOpCuz0hExV82'
    'LSMhP24k29mMjtaVtXvx9My58mEF8TLyau17tybgwuqxQeGPfI0nun7mHkKlklsIZYps5Kp9NjIGqsr94HQ7nRaNVL2DyVRc'
    '54g200YQRRX5VM0prWpALMsNaZSvRjUHtVbG2pLaL+5y6yyngUL9D9cXIhkCOJAWRH2sxXozOGmsKi4wLddCTgVdl1TVcNVg'
    'vRGrarUm3fF8AxRhgWPtcQmJaKAeVP5wdvX3B2/fjj69fduoPsTnmnP1d+LdfxCEY2lu5+gZyQL9COCwUVP38BCt7zZax6kr'
    'JwcPmiodMWdRDOdedmmCTlBtoOXGWigSHWSyheZxBWsVacNoHtEoU6vUFOqggAnU9D5BX2q0yrhnzVFVf2yZj204xmV9je9W'
    'pBobq0nJE8E3szvn+7oD/5AcLrVCbx98k7598KDmvDp/Uv9BFyRzr1g+rDnj8TX8QnVvBqXq7tJm4kpB/7Xh0NFPJU5sIyod'
    'o4UBVHVbkeE3WyevAODRFMfnmN+Fksm7++bZnVQx8QPrjOh3Hic4eHqh9UFHR64v1RJU6a9VSQ2ueOBeiQeW5EzdNc8z0GJ+'
    '6pVmHj8qxUdFHSF2TYcQ1w/aGFSzJJ+gU1J2gBmSKobuBHTGLZv+ymzabC0P+BQKf/utPvEEvOJ6rgSoSSZ0vK3yYNyma1wM'
    'SIFN38U1Mc68NiTRha4bVImrs7o/OrFKI410O6mwfAx8FSVCt6ZXrZozRR8O3O1ZFs5wy8/DoZCRbXje9d+po2B++62AneE2'
    'B/wgiAz0yOnYd/lhpxQBCCCeqtMIzJOJ6n3UK168WcPmRBoifeVOo7G4wWDBAzU7i2gJorLYrQT0r53HqAqEN8JHWDpt1qN4'
    'HSfwB2RsJwm2s40TBiCFxMF7dvRVlxfylCjgUX3S/W+oXLKczZa3ZLPA3ENoAWBxrxuwDWbedmt0tpsHH5xgNg1SZ7ppSG0K'
    'yuIGObkoMgb1ZPSx1UShkUbMihn6Sao2Y6BWFEqVFqGIL/L103k1r+eicldGmZG8IaygUmZXY6QxAjpAUlKiZh4YcDNPUAcq'
    'lE50sZQ7SD+BcmSzH3UVGKu3TSVYQREmNJVKG36E6ut+1wD5ch73bK27eX0F7BLa1+wlk6d6iy8NBX4lmM0q2rFPXKvSwQ8P'
    'YjnyeFz/v0H9X0AkjXEdT+h+s490IgwBjItY7na2pBEavxNWL+LB1x/gCGKUa5A+t1LVCe8E/vvPnHc4rtMI19UaZgtXnbi1'
    'q2Sa26fsAo/LLYxnMxbzKHgAe+zTLpreTFe05S8TXPiOMrTYLhCTSmm7Wsfvp3ijPxRu5Y0VO4yP4XEepO8q4vXriz+Of3x2'
    '+eRPNedj9urN+avnNSd7vnjx5p4xtVl/yEjhA27UQv8CJWfap/2tvj5/8/zx6z/VVF+lxvt2Pd3E462hma+gJ3bNEU8Z0i7S'
    'FGYTZWppQiGKKI12GsfvhN9/CFyM7lSuZ8sJ3gm/pwACmqI7p2MQsEw9g3iZUyeQ3YDYc0UJ2m9331+fiy0V9tYgRL9iHImI'
    'IyFV8QKa2HyQ6zpDrROGakAfhy/0IViDFCJtb7DH3PWJtWXoXBjHEVu8SjTTJIkGv3ZefgBkLxw+JDhzdHtGvNPl8+vz8z+N'
    'z188hbV+MwVWI2Mv/HM8wzKwgv8BOEgbAhTsa4uQiR/nAYgHFg6SeCp8udfxNTI9WEgO04ju7r1drGNYOnEkoIkpdjCyRn5Y'
    'tN/RteiChreIYTZxoa1iPtBwl8gxe9faJfpHFr9MG1B3QbTqPHJcQcLcB+BC8P1y/JdXly+e/Q04NT09eXZ5/tfzJxkXMtaX'
    'mE0oSeiuJKgEpOkEwULNreUwt9soy05gxpRa1zQJeWkjnC1T7Itcr/EsGacf5pOlvN8Vdj4oAQ05BkW2YJ8tQ5Q2kJRAnlyu'
    'kfilUaObkrmJuDZDi6MEw4ssaVaEbXW2XI+xXncekvpR/vNlFuxilZTYrsNRfDOL67AOpiA3/TdasmuvfJ+LtT9nICV27bPg'
    'A7DTLzZtR1UhTMPnmLenMRvG7WkU/84125XNdtsHN9uUzSrxRjNNE11hq1nulaHBFy+veB58/wx50euf34yf/u0FrIjvhAkM'
    'xXpwKF5M4JAWboWXf7SWHLp+3m11hgc92RSTARO3fAfo/ib3ClDxA/MO2XGrwlUWb49y9uMaaO1DXatwgHHk82CGSlwYa/QB'
    'uMQ0NMas24KSDQRf9XBvr7KBGAdeUdLSYfGh0GFV4Qv6K2w08t1mO7Ohw94Fqh2tj6dav0aG3jezGWB6zBBb02flVJsJvM7L'
    'YZ2h486YLGvOuEbhS+7gwMSWePCqjA9d/Pjjz9kCEvZ5poaDzjM0xgbsEVEFGKjn1kSbBQUkFv/e8Q7bpUoxjZuJW4BNnRAo'
    'PoOGSFQXZ3gSjPiQQIMXv5IlWq93sKBFDcqLXWo7BbaMPUUcGw4wTlTCHduWi81ObL5qz2Pgv6cTg/69NVJWz3TM+V7/curk'
    're93uSzs2FH2eynQPm81wMz6VmeswE/unHpqSttMkmDG6ziMpyu+3NGtYaS2HtVbIPiTNqpeeRudVt+mp2+v4MfbUePhH96m'
    '/K4B/8CJcQBnXfheydQ2n7SDduUPZ3CO/wRn9Oon7WwNr/Hw/Ak3j0/y2FzVSzPQxsPqf8grC11W564u15qC3B+xU8002mfH'
    'HSs6W4P8S3KIpDJh/CN0B8IJ9npKG7dUywvkp8vZVtws+J7z8KFTGeAMoJBJNTIbXa3sD1DW8w6iCdEVFd/NIVXmFI8IGL8t'
    'WKdyfWdFhuZ1AopvY2hP/gGawO/cv8bsH9t0UxnUHNeTOoSvxWFjTaH44Ex6V6fC3DacTVDWWQBtQHsOMJs1CLawyUYN53xB'
    'Uq4DgAUkaU+FIfxAFnImfFhD5QNgHW+aQdp7/ORnaAWjMPAGP10g5vGEG8KxUp4oaDqkSSU9DOWlSE3ae2EPx/MlEMdyMQ3H'
    'i3So0GKxlpSVZBGqPpSIO3Ub7iljyVI3q0RoQl/RAFV3eALGdrPp3l1ZFctVkp1DvbpS804TRw45r8nPqGmyjD7w+tUVyrCo'
    '3lbo/u/hW1zJ1T9o9yUPKrqGsPrgbfrQrYmmOuaVL647bOGY7Z+Xe106SKhLCcGCtA2KlV3bFdriVQph96Cn2DTdmLFFoH2q'
    '6xkeGTSqCPch6G2l4t1JNABjQyTp9w8V71MT3+VvnwB3NvUZIvF0J4pPDwAg7qzMnqWn4vYq/5rvsXJv986kNN+Q1iDIHAjN'
    'C3aeYBtFOM8okb/i17q1Xq1fPUpoNQIAZo49wlbsc2kBFv/JwZ4UamhAQTCymrwhpHedMkiCCgpAugKIiAZZ+N7j73agohJN'
    'WbFqX4DWCVB9xCtiO9A8bVLxljntkoEYRgi6wjs3qcY0HLXqiiuvAI+tp+3wTq3w5G0aosRB9b8+JPsVVLNgspK/R9Cv6Qhw'
    'dnuR18hzYf4mX+1fBZd2R0q6TyB99GqKKyTeBKSphN0yuF7HcepWLX23kY7RL5NgD+mf8AiSHFpE0Y2WMUuikxiNN3HrD4MV'
    'yJsq8q0phFLzyso8TdkKNiXNnjIjT/FybOh8vM985oMNXaWkJOpXlCIQSSNcbd1qAzXPFRd+P3wEpIEeohqRciMZyLwpUKbr'
    'wu29Ui1xihM4ds9caT9UPOewQSLfhRjec1CrYEWi3WgKW6EqXxgtQcZZbxfS+heFoOxNtF6SOkOoP0tMdHjMVzrskZD7qHfy'
    'ZdVUr2wqXFF4vh7TkXtl5UcQMt/S/cT1pChVE3mw5K70q/QqCAl+dr7JiOaKJnIFYifwDxz5iDT62Bv9UMCFdwvXz6dpinQu'
    '5H0gtPqTl7+U9EAQN8MF6iYvGudyCwv4RxT9KOAyt4eEPx5PQa4djytpPEvomiaZ3mlYwtcNfktu0fjD/Ej0PzRt2+iDvGGx'
    'fiQfDLwxhTPbBlgpsnS0E8Cgxg38q10hE0izFs+uuXjoA3P60s/MuEs/43FgKs5FKuRy44l8q5lLUvF0w7SmFz5H2PmCMc6f'
    'dfhc0fopsb8mzz/rF1TqxnRwVQNkm2ltkmO8BhGzrM1uyUUE8PsYpoAjPnhI+BjaujJmN5ZxVZA1fqUP7iNYhY+shoU7VhiL'
    'PKiK4JsgQzmtBVEnAgvxtB1uluuifigLm90Ib+Lw3Xi53ay2m8qVm34AtMyjegTjCTf191P2t6jX388x7Aadn9DEoqo4nrx4'
    'd/8Zz7dY9h0U/Y2GFeiD+vP58184JPwxA8KJWcBuEcYl/UdblHMqgRzht+m3jKQeK7jFHmdc4uqMry+uXKCJbUpW4W59m9/W'
    'v4Q2hLdvFKfvYCU61IjZJerPckZX0niZl92QAwb5V8W8CK/mjDATvjlcb1e4yWPZ7bzGQe5LyeEiqyEFqdtFpg3Mj0lrIN99'
    '7pq1ozW9Xm4iOC786jYyXm/JMhre4uBXt7AXVfT5Avm8sbodYzB5Y88GoYqczLRbEV1eQQrFpSIYAD4q0Ydsvh/a1k2B4WhE'
    'hCBQzCehZzOmbg+p96jcrFCDj3jvh5YMEUlQPysZMOfBWakRVzYuqQBGwEVZCO/DVxvn8jVNZZlcU2I1HS8qWTu2MCYHqZMF'
    'gdeXREXQzUg4vnNeB7PPhJ6hNjz0bi+siZWykidso1xigplNJ+tgPWUHPU1krF7V/ZEhqKoJwdAN+QmxuRrY5lxX2z6CtlU0'
    '/reNJvxJl6gIahA9nVYfKrXqvQ3jquufhXD9RlRDtZEIgVv44NpQhjoaWguqG43V0pBpDYt8qtKYprSlVqrs/6Beph/mMM53'
    'lWqJveWjbbpGdHXb+5HGlzaiWx+qB25mmsbZgg05ZJRxc9igcx7y29JNbL2a057wzyTXNeuWZkNfDhuiVzBqwkD1DxITzbqu'
    'qzodnb5t8GU32mlgP49HhsQA3qYF17HSDuawAAcTNIKMTETAjqiN/9dd468daIWabiJA7FBr5OXFy3OEG8EmUXyPo8IKLa+A'
    'WdnnBh8hZF4D9Zqbyr+CVg5D4ssiGUkkMjxhEJQEsCLyO6KKllK0Q5HYyxloq1uoYcap4C0xqnQ5ex9XkMBCQW1FTmlAyB5y'
    'riLAh8efQfEZvMOIXutMJnMjD5hMF494xytjFfT1do5Lwu+9bbR2LAltOMeJvMs1kAGeUK32JfmNC3ip32u0cjPMjR+1bkqw'
    'eOjS+c0XkDmE3DLKfcwWU/HD5ywpxuzhC0pGfhwWYodqWM1NEGvbhtaoT3owBVpvjyxygR7psDTwg7m3sgaXGyGZREZi+IJO'
    '2OwdzCgBXxbVwSJ2icM7XQYKLbKJ9qGKLCR0FVkITFFyKP4tkrdQfhRqpEMTfcWa3Jbt7kHUMSdKqWjLIBnRbPVwO3JYQhlM'
    'bgWiWDH0TRG6YCXjnBeECPC7Iw9ROShedulyC4dpCciSgqmWq8CWY2YFI7VSscV5vLlZRkNOOVXjzGlDF28RxuvgFngZHmDT'
    'FVo5iG9P0FZ7/PzyxeWbyxcXT8avHv/FNa5YpSxfbEycGfD0NIQ/kqnT7cl4Mw3f8bWN2hLxvJUT3qWrYZWUxOh8KI8A/sB2'
    'lyNaYIzkPJszojTsNw3vZtlH4O9DbQuy0Dnv9OiTeTPUBaea+oQw9tS2d1QK3+W9tJwQ2dpHyCPCCraWvdfDqpVFVMv8ZWTJ'
    'QvirjARN4ttDdrKSSeIGcVvEHqHNFSJG+iF9xGT3CM1wrLoflDkqWd2CSXQ1O+UUd7WvneeovhYuEOxUxFqxFMPtLaJgHSkb'
    '5jkVJR+kGuoELNC2i2jJwDY3U1kD9sD4brohh6SbZbp5FMXvp2EMu2Wabm7Wy+31DRZIpX16USFKuvxpSuCysZY5JFt26ldo'
    '5TwVl1J4bYHJEalNesm45e5aHNCoRfo4VspemCTyDsuXPciS3QCel7PmIhiMW6e/BfbNn7j6MjyMMO4USLwsfikRye/YD//Z'
    'cOzDyN8eGMQl36cuPGVXCSefjQOjtcb8XTRdV6q7SwkrFmvnK2bvHzHWcKdHO0C28WdOiyZMB1QVu0Kurto+CuvRvZLfRirC'
    '5T7IGvs/SvAnKLyjSTNAXMHCo1ddlGcZQ/eOeLLFyM8UNHj8bpIbtN/s7wWwpECE6SNcZMLZ4UikSwjCu6uO5qT5jhTRXg6H'
    '/Xjrm2v0e2swo7Hh+VAIu0azsyOLNA7Tz+yCrHsQFuRaFTuAsVB3Nb+Pc65jdBXROadQrfMtLcHP9UkGfZPCd2aDNqwk7vrs'
    'Y9az+0fZR9R9kkCwM0wgx3A8IH7lf8BZ8H0wU+Ek0ZnM3k/TdCUXuC7rqz323W6Q1th/x4FUIY3MS1QzAlLmepV1oRAB6fO3'
    'K9uVJwVhKSqzVSM2Z0NFqZnHYVHEE0achWVho2x4sAbIAXkQT018vawFIKDrCuEaLwX6cpuMvLGQHTtaWxiTwPn2W90oS29R'
    'HWtlphLXEpUnntmax2B4v13zeroTWx/YeBaRLqJMGUwoa7FqCXciqPVK2l8QmlWYRYa8q8V4wU4f+9gebnz7YziqST6U8ykf'
    'SNPSm2Mj0bX8xdNHhFkRh4LzJqS221BSQVy5opccsEj1DZ3TM3R9oSxluEmWCB6rKQXII/fIV091Z8kXly/IVdkyBGU0kZld'
    'vKFfFTjdXsPRKZtedKGMYZ1ZtLtfk58oJ3OXRgWUgJxMuW/iNVrOT1BYIcRrftp8EZs7JHyNKcxReq6D4Mh3BHhN++jixRtn'
    'vk03Iq25g1eN5KIsspsHlOYc+5oDF21JlYq9KHiDc2hPZYMk3RGFX/gXzhv3hg0tK9XPFWrzq0O3rDOgVG0RMLDESe4K9scg'
    'jc/pJ/T+rEgW4zGe7sZjERQ++7tatPXSbGKIcHL2MHKS0F/ULbeSub1B1SnlGNDsgejiLraK0IJFcHDwBv9TuRKrBU5PV+JP'
    'w+tUr7zREbfNOy/V5XBOaT2qATfQxRgjoHVLr71/RPqHqheXx15/axeyonn0zgXJXfjlHn5m/mWh3P0N9oc3wJZDMk/KRPrn'
    'i8btzQkvIjXb4pdQdBEMq4FkLqiajFqnGydP3K/LdsedONPFjaLLUyOKjRgA2mZihYRBB5WBrcUa3R3ZBSVkGqZJXPlQmOni'
    '/Zpum5cZ/rJD0ujomFqldn0F0OVG4WxKXbD9KzdGmCaEM2TKPCycWrl/icqn6oXeLe210RS64D5//Nfx+a9wHHh9tnPENvJ/'
    'usXs8XgWyVy+YqvTV7ojZhGPBoNQjiRBnOzEuJr4BlD5NPmAfkKV6k6e7ASpExfZxEHEZNhJ0qUe/i7Rv5T0jQr/J2qypyEr'
    '200ur8l6WQdw3+ZkBxyXQ2KUE1BRRhJOjCKWYdpwHjvpNsStPtnO+EyhQQtmZLIjbdBB3BKxlNbbxQK5DMN3U+FkTwbKeoDu'
    'bPsmxGliL8dbrbJA5a4nQN4BqkdhbPOz/CEMA35y1AQuwGwfQ7Vq2rh8C1KwPqAFDmJlacFrWtKxqP7QJoDxYuXCygDRp8LO'
    'cMyOwM08EkKwnHLDJJukC9IAaEFRh1n/CgzWhlf71YE2yPILAy341zAb+p5W9YC9hVYz/BmhYjUJh60QlFifF3aEGeWQ8yec'
    '5Q9Hx5x5bfxHKgTYs9lyaL/XqUV05qvhYacVYetQcuZiYKUHrt/osBXeoO8+XqznUU5ye0G2ZAM9w14ScWk9/RdEOk5mxaZ7'
    '4mr76Ku7grLOYnGZmwDtOrFEZJB5GfM1C/eO5fXFeMqtcxRszTbhKD01W0ewoY6YNnnOQhY9C7aLUDdkE7tcRVh/1pxf0X9E'
    '/L7AQAP0u1qy8x3Ykykc5yZpzOHnMKhRELG6gaOFEOCMtoj1CTcNDqiGKgXEL6yoRcq5b1kwkU8sj+CTCFuW3c008z4eBulW'
    'rd8yTlLdFck8awskmLgQultGUMMYBX1rHGiR8U0WVIGQVE3NBVRrl2wCOIxXGaUV7KPcK1skOY44WB7X+zODFVaP9mybsE+7'
    'MKsyQzOy1AIFZ8LQBz31VsDASGjUXfHYRJFteq/0WHy2gwH3nUth5wWpjfK+uHI6M+g0o922PoXaRzWLegX7RFLEeT0a206M'
    'Q+mqDFSPHdbgH+LvS548Fy+fCEWlSNq3XUxhs1KW+wqkW/BJzlYgDl9fg/JZrsIDcipCN5TbOVr5v0c3h6JbI91tF5hWBMuT'
    'TqVDWuUNdf1WwVCkYuGfHCydZ0oOlLIFcvWTHqqi9NfGWS3/0fDAOmS2dM+SuFwHYUFjVsWmEkbFGx/6Fb7qBXydWE3VZVWY'
    'V+9wNcZzkXjZFCvEqQL3gDm7930HuHZu4wD1kAmgPCfClhyEboMppokQXbM75pSg7wjUSSvnzMPsitMJZuRAR8yShTgqulTn'
    'YOi0cziknFufBk//chi8L90EVT5SncFSpNNcnFn+fuWSdzaSkp3hVsu2xo8GAGvde8Vs9wIr8cEmuHw+BLA6No+HbQYcOA72'
    '4SxcBGZAvqNz8xsMaRxlqpQJxqG0M/QMlTVF8CJyR01ln3T+NV1VlPiVWxci/G1aM0aVG4MIxjtkyJoui0X3sVvF2EfWaOMy'
    'O7EuZ5cafwJIpEFp0Prxvipo0mLQWbUmYsltbWKsskk9DAJTshhQ2WfCyZVbDKJQfjLI2rTqMJFa5Go4XMmJ5Mk9/W2BivH9'
    'Lj214vQHQ7zY062ykEPuqC5K7IkRdGyDVsPh/Cmx1AB5L0ZKwZurZU8ny4NTiAJ5xrgroxD3jFStCgA9aVuPXejOZw4rVdFa'
    'UoRlabvynVWpuCxvzBFXd56YSmLPC86Yjz3/GZAIVUVIx53xpUQlnVFqlNQW82RSzJLtmlzWWWrGLXm6IGWRxvvEzbA8YKmz'
    'FKt9MXrw7U28cB6/+JuziG9nH2Q+bLHZOORkn2rg+KKX4ghRwt2Gc445gGW1VTAlh4PwXbxBl5kAWC4qzDbAslMS777TgYFk'
    'yCF1gzW0l27EnkTBm+UrMScb7CedIDCAJMv6sCs2Cnnu58FdxdQbzKeLiti4rUzH2LzFBpehkLs0JCimBkKDa9sByoWC6p4j'
    'Fw9F7i/HH7pemIKDOnrLeYmWUnpjbBbVyrqIwAncKhmPq8npFsMZShFBvs7JEMO8TGHJ6R2NdQQN9QcNLmBBSEFDlox5fZUd'
    '8M2GNL0C9HCs1sIQ6VhpYnSlkxEWyaApU7hQk1OooIilzIBgWG5MQKqwzTYduuKKoG4P4OWaYTHutNgnDyleQWTcET12OFhg'
    'zqZDEQS64WdR6WdxsNiuGs4rWIpLqa+ZRRo85r7rVASZc7YLjJhPpz95G22YnNBCDkK0BVFJAjRwHCyd/cNRcYqW/phcDv5E'
    'ZEEiuuTgfM1Xm9wd0yHmIeLsw3CMoCLyXU7PTcfHXNAALC+LB7Rn51qxmjBwyUres/PgC8isN9LVP7tgtId0aWTJJvUDNFvG'
    'mMDlcGbBfBIFZ4YJzT+WwOwyTav9VC7KTlOQsoAB2cxGzM6b0STWHGg8mkaCJy5XbrHnFqzkMGI58cvKSVSedy4/fBUyXtSs'
    'Wuy3ipFtoCU4kwBxrsUadPMm9iCyUBKSqohwq9vq2w2J8z07ziC/uhNWOf+pnhx193X2m5iaaiaKNo0Vx64rN7cujpCr8BZ1'
    'JuofhCBzYtbzaLo2D9YKGxw1zYoUWyi/vPvHLmxIuqWyZABiEJuOFZaa9uAnhxtKdcBXpfsMit36GRm6Zl08ddxHMoWmyPGe'
    '50EFo2ZKZZJTM+WWi/CiyVYJoNpWJPMbUkV5RR3q3FRgd3mvoa10GzrUNcjCIDKfIDOPG6ZGCFJ9UFpsH3dfT3cG08lHCqrm'
    'AwHNCkWMGIfETA+IqLgrEJDcpNlRm1Otut85Lu8j3ARe7J987fzlBvNooXEJiIlrkVZgsoS9HH79C2SFi9eXznQOgk/K4eCR'
    'yUNDIDuwqUEkEiq9n8a3sN8ByNsZxb0es4jkknb+Ft3uVtuJFAFxHzj1O9+RTDGdy3RiWfqvi5dcZIAQ8RR12mw5qCZFSPUF'
    'HHhvJnRTjEIP0Z08ZfGFqDBp5VBPZBsLAsoCqAv7+NPlq788fmU69qIpfTRotdvJxE8mraDnNwf9np90glY37PneoON7/U48'
    'SGKvlwRBe+CFiddOIr/bD5LYjzwvHrgK8stz5UhJMelagKhk0O63OpN+MGn7Ay/qtgZRN2iFfq/V8eJuEAX9rpf0Jr1uO/CS'
    'aOIlQRh5kyhsJUkGmJ1+EaYM0kL34nU5/DodhOvCBr4uUF8nPNXFEaS+Dm7r77tab19d/nTx7Pw1mt6JcN8h52MZ5iPDCLhk'
    '57RupMuG12h2GxjIn+ychoCyrqfJ28LWxO0mzV7YTEK/0x8kg6gfdzrNThz0es1BMklanXASNXtRp+P5Sas78br9MIjaTb8V'
    'dLudXqsb6SoMjvPrFrrzduO93fjUH/w3Cdvtt5ssPgt7w3p37eZAJhDfO04+71jG2e3CxFvGGU46fi/0mkk37nv9Zqc3aDWD'
    '9qSV+PB35DdbzTBu+50wAhS0/aDfaSeJlwDt+H2oGQ52j5O7c+A4mwmNs6qm+ce/vaE5phE0cKXfxHcVN2l5iR8nQbvfn7R7'
    'Xh/+HbRi/Lvd5acev53I55YXYrQNGQvyNRLXSzybMnPSOVWWw+en6R1m7QGWtF2jhcQENlS6olrEt2ygisu7jiwtpjR/7PaB'
    'R0vzDoty+XCUVUHeY1TMAPeq0AFZhVqls/TVfrX2Fau0R2U6wFOnc2IP67AvA94o188dvhxkaiDGkSHtVyyGnBE+OAu2EBZ8'
    'LoVtEM56xPwSOKiJ+3ta6Y+kadEjhigLqzRIKDWQzxVZuVIdipa5gm2RxAl6Uvn++DUNls+ZpCZMyMaPlZFT9s+qUMLCGucj'
    'FIErUMqgiyw1WnWDhesPZ5g+y8HLj7iJyKsf9e2rodM6KbHvkIW4lFSiEmyRys+8OJNWBxzQVg/zrdL9KZA7Mhkut5wKVli9'
    'sW+l5r4mXmBuFokA6b6mUn4Kt1qaFoU1HJOGs684DCc1V3U+iTncbbhGhfX0FtYRTDmLiB477e+Yb70iQn5hmDRrCnh83XjO'
    'JGAbpoySO9JzcwrkppzV2kD3NGIbDrrto7dXIkicXoRv9fzWrjmZaVmh/51T2cypzBwgvs0wlKELDg2rGfDiiquPAFe09uys'
    'lqxOFo8YWk785AUjq6GdiCvalnXEI9aR/aU67knJ0Y7o3CBfIrRh3h1PF6MFv8GCBWbDy4o/URxonaRr0jxaWMnSCy1fcvYo'
    'vt8fkDZaXNegKvVuOt/OiVNWpB12je2YYfYq0nC6RvbL+fsKM40z3v8go86lcTY4LmdhFuMHQsmbzvH374eqY+I7vs+lqtx1'
    'TxVK/gUl325c2pLwjQv/A+Ah/uX+l0t4oBif1G4ZxJxdsuiLYdZsWCjjJOZwIuZmVD0wZb3ItkuOqWt1by5MXgvB93el/cbm'
    'dyTu5oZkXt9ihmjVBCcAr9DJ7dMncXJzxepSLdoy1KqtEmpqOepFbExLxm5rWnAjd7eeptRaOpe0tBTP+UTk+l5irBZK5q4H'
    'zYLlIhkIdLnTpdWCPASeurx2BBupOb1mfuWI6wXaC/7OGbSphbMtbPiITHqi/Nrf8WfhoS8RLSJ86SUwosRZXz1cw3n8zPtO'
    'pecurNwaB2sXqaW2k0Vm14qzwEWSWXCNeXAazws6Xq5dEojUhmxkg7h2qGIl4/e2aKa7ZouAyG0hA1PTdo1qtm2wEJTTTMEQ'
    '+b2efVoKmLKIX5a3vsTFXS63EqfwPUtONKsZyE/Jd4GOhCxjmd+uXEvnR7KG7gQipnKXi4fO1KrHeXkI6Ae4cpQ3UrgBLREf'
    'aeB58dFKL0Z+eePMk4sPIUJDkNaiphRPArwWXIPNr0pqk8+DrHvlCt9/4EMuBZAdyRBgGTJVrA4+6/ApZmgFIQMHwhT7nZqT'
    'VaIDz/46AzMXuTgW6OmdiWqVDPVNND27Az5EUtQ3KT8ITn/qVb5JV1V8lecpB8XHuM9Nxu7cd5vlu3iRy30Hp4AMAxXG2yfC'
    'RHVcyfLU5fPTMSgh5BcE9bJuiKzgwIvTXDcydBn5nRhp5iuBunweKGsKPdGWJQWUSBmfTwCltlmuycp4Mw8Iq2vzShH3J10V'
    'p4xLRAeCNRp2iFRRQh6AFRggGnRHVFQ1jF2FYMzsi6xNHMoFd9P51MluN+CrMzEO4aQ/Uoyc4WOqMe7HqWixhVmxqtp0GQmN'
    '+LonqytnzUjxxE3Sd8ryhHNoK9CUBXhGbUVaXKQ0DY+k+39s50DDs+WGErkq9cpTUmGLvNKoPaHMy87/+eX5y/HrZ5dvRB5R'
    'UlNR2l28FmftlvNH+Cx6pNQqxq3z52dulvLarmzTWuJmS3pnlctZl/izJMXFxO4HEy6r17PczpYQIV+YcpnyrsJ6Y7mWs7CW'
    'J1pmVrgl+f3KFCJ35ltWOhY957KR9HhHbmTL1Z7NDZ+pZ28iYnbHK+Ys5tqFothr8UlmiqYuindGt+25g7WcxgeO5LfLMUyc'
    'TeYT5kTD8MjZga3E8uc//3NXXmGBEZGi17tLxH+IhB45A9KnH35wWs3qQ0DLD0OFqs6xgTFEWuGDkiDLRggluU5YvDCEO6Y5'
    'YwQin3eBmC7hCx1+zVzKAKRWNutWvCEgxAg1Tzd5lH0anlRm5Imbu9ErTbghJlLm+BHdbxFBeuUBCw7cMGfL7O6QvIgWIkEJ'
    'MGXFsUsUFcQhrAmaDedyKGQ9HR3fwcwPM5hPptfb5TYt2vlRg3J6pYto5g1ak2QWl/mGHtQx5NV05VEQMwy3UGO/nMfz5frD'
    '+BaO6eRMq3KAi9VshGRSeTviuT0E05Nnl+d/PX+SRWT66fLZs8u/VIt7JocBQBsCigGAcWX6Wdv5CSNff5iu/mdNF7kFRzI8'
    'B8yZ7jGbnypjwSNXEvu1nL0ENbYzbSTKfimJqnnkkidzLja6OLEI/IrMO2iCWMS3XumLsE1MieAm5LSdRAUnT4z6IsxVSPSF'
    '44DMsDeO4vciG2CDmMNSe5ovo1h73OZDS6sv13jvpZ5QqaJDQUmLrH3Vq1C8shnxbhqvxxevX53/kdit7IbhMCw/YEPCvZTD'
    'CFmjCR0hEQmmhFca0nxzHV9vZ8Ga0pbrFFWkcaNXcISsOZ5ppaNTu1FY82mp6PPIJeUXrGJ1q8opDvLBHxAIkeWVq92clmhX'
    'j0GWJK4s5EFuvdEWaun/vnVmLDSKl20CMe6GFZkQJcsHImSdgLKnAhnLD0TF+sRoEBQNyzcZCef5woq6nAqWuyaXMNRoCJFC'
    '6mOzA8yPqNz69fljmKXraVjHk5Tz09NUZilX2S8Q7HccMQLGyqaPQCn0wAI8xpH7cbNOssOMxoNQmkmFoW4aruH0aFjk4iCQ'
    'M8VRhXtLasya8/Ahmutc65c3B5sJmztMBjXH5bRGcnZWqp9y29e5m9yAIwtTFM5q+QxJFFPiyq8PRnQr+tGrDe6FdRol/CrE'
    'JcDpEy7sJyXuK6ooLm0LN/qcFTZn90VKxpGGgD7LCU0EZZdzRtRm2UmeXrw6f/Lm8tXf7HuJSOKRZpBcRcLucQDRy2E9TqIh'
    '2fidaFLxZqvDpxAlJWEed0IiEmUv3LPiRqTzY24T5A5/0DL4sCZ4iHuXH7BQs8ypaM88CWvHjBfCDoIxppF75JOrULwTI8Ht'
    'WkaWOyAyC2JizEctHNw4v+0TpmrZM2OgMHDuxPdCuC9suQq0se8ab0U8GNUf8e4LEailjbYFK5UbSq7RmvmGmD6N0Iivg/CH'
    'Tt59OwwW6GZC9wUG39tBl+Z+bt+h1AyoBqrGPZyNjSi6VXVqGUsRogQhvXDYPwjJ2VCJoRT3a2lJZDo6kEEIuwMhGzyzLaL1'
    'kuWZ7mfOv87oAIHrDyUEQPdQSHW3+ZM0zgS+7rAbKXJymEZm5MIGgYZ3cPSXdRZLxK/53fu6+QhLtTymNOm6NhXOac1X0HUX'
    'zxeshP5haP0slKhlEEWUTsr9x5cFgjsi364ao67+N0xDWVxtNPEF9odRK5DIlgAGLego1VeIiTpQuiE9MXlJLVBgQDFQGAyn'
    'ZEashB2QhxqFTFN0bS8WK2NiR6xgE00FiU9nngy71N99x5Fkh5S6c9HvJr7RqUuS41V7VJU0JR+1wwPwux00wxyFh1bKTsrq'
    '7+FtAmEHjfG/j3x/eirJlpUihuRs+kFVxHaAzcs9Yv+w/+ewdFqpIuGuIYCYzL1w0hLBJVF9mjbiu5D2zgpyKN2rK9sCyPkg'
    '76BVDH18TFhpMg0RNoYoKsFa1gT9Eo+k0mjGheOjPQK9nrZ3h2NgYdysVzs89rTQYzCaS6hZp0PRkIZ7ZXhlg8G0wZUKN/R0'
    'oy0OAofqpITovyNt74lQd8iEXJpO6SBdmGiGcnkhl4cDp5ZBmONyd6pGEmHshJEtOEvmW6hI+Z27I0srKLpoIoz2Ea/lWGIY'
    'Dgs5I6UFo/U0nwExUWzBDw8cs8tzPE37LeYJ75xPgVOJyLBkLzNbBpEzmQrLcHydxqtgjUbkKCXX6TvzALpOaYjsz6mAh65o'
    'lBj02eXjp+T7G6Cl5cw59e58z/Nkvx4RDGaa8SKMv3MWMeWhStMtyE7/itdL3oXT+HouAyrtuA7Ubk6s10Dya6tJLOfUWTzs'
    'dO05FxfaJZUN1s8SFgAAWGLiKJIJYod7yr0WF4n8my4SxWDo7pB+Y2+AGHzhUMrv/JHzreNnvFP7xNevQq1WmrbS+V6vcKoe'
    'OuI2kDIe/qa9bVt726LeSlrEL/L3qdPHT1rBYi/F4stQy9cr0sY7G0T2PisLXRV32+a71ujIGxBWOmYL4/GPFzkh9RqOghr6'
    'nWzEdQ3T3DgM03zVlCzk0HymyKRqeylAWIHw3UeWV/XKpes5oJB69soknVPZezU2wat/N/apt5FjnurTLtbJV4/w1TdjsK8t'
    '93ls6sRSrTeynZWAKiXasLD8LQjWXlccpAyylV3P3wkeRHRoHzKj1EZLCvrNN0uCFsXEadSH2BoqZMmTqngWdMWRQBA9ZAMj'
    'qtmRUMOr3R3FpPWNbnOpkkvq1ZQVjjS/MW7j0OE+62NGm6eFJVU3C5oU+5Wasc/AsrEhSWyZ61ulFth/wXmihUXJVNwJC8zU'
    'BBB13nNSi8oMhxEZlVnlJBJWifkrK4rxhAsrM7XPrFvpULN7ceYdlfNmCxYd+rH3hVYBete9odyb8ldcChfkfciWkjb16gEH'
    'Z+MCjA9hJmhtd6naChzoeUD189dhCpa8BSsDhrWvVGlJ6WeFN4CIZo9WgOGnWf18rSgJ884teXbj5X+JXvR3lqjz7eS2Bbs0'
    'TVQ/yt3kUG5VWLruR6CoefAPGLR2cVc985p392f0bbqwfSvYze69bcO5q+1S0ORCyJDay77vM0De8QtzX6B+grQjFh3zsQON'
    'tjgouJH4XoQj3W5W203lyl2v5pSX9Z8J/SP+/ebji8fPz+/fbr75eP7y8snPL355Tg+/nr96fXH5gn6/On92/vg1F3r86snP'
    '92TCn00hOzTkgjS0PAwLD6f1XAge6hVx20IUCNnDX5Ny8OkmQuha3ZcXL8/pPZzBi++17uTxzyjTlzm7zBFPEd1s8I0CWY5q'
    'b7kXuTfQ/peuY1TwOa9ePhcqKWFixOf43JIWu5a88GTvdpEOXn8g4QAITWWCp6dikEBhdCxLHU3eZEFvSXRN5uNfBnZgAYvy'
    'RU5IqdFLISCoj+K5lpdRhrlnexOy39rvmjInGovMcfyPJT33AshmaNw6MYMb8j8AaTXnYIpleccpD7f0/LCFssBEVJlviCUk'
    'RVX3tMlp+axKMRHscHyoyieexe8DMjn/mBP070HM+JiTi/YJV/dCjTCT3nemQRLtYMaWJYyFjtmz6KBg+Yp7E6kbeUS8NY1r'
    'CiOfpdKSFj1ivWZn3wJUaX+TvaEDPmOiok+LzGnBX4r3FpqGulz2zbaYY/0ZFLuihbCVZpDbxbsFkDFzRV27LG5lBQbwuGPq'
    'JDk5BXn/1BzhxZ5PUqEFC9TSUyj+LoagekZMfRJzFEWVr8DQgLqZ/wq6zyrvJN2F+HMRQ81SeHbMQg/fPsjWLOkUyqL+7kil'
    'cHi0flK5My4sofqtYfq5NDsBiSDo0ulkpIfmt5XjOBGjg4L0A+YZxM4Q83tNO8nxwrpFfk68/gNi9R/j8yPMcA8O0p+bqdII'
    '/btw90V4E6ElZTz8XbRwWGh8ooid8ATN7AfHlS1h9o0P+Rj7MnjvsHgHYkunJPgGRVgQKDYzW0uuokLRslgwVh6C1d2dRfde'
    '0SWWPakvn8tpcgmJjLwezIV0N1dS8HCWu6EZZSoL/ao7TcogsfyUL8OinSjCboInpfGBjwwOzC0K4cUaGPjIqMDcP3mR8oqS'
    'weOFiRnnjEkOTWDeczQevAacpUuZRSdyJh+oGsYcw4uWpUi9J30MBYkxUoRnrQjlq3YyPeTvsXtvllsAZB3KYo/bbRYATUQ+'
    'y+kBymMNi76VxcllKtYCVZo797HDfPDgwWtKzYUxtNZs8xFtw3j9iFwRP0isY/RqEWuH/QEfaRfXMepZka2CJDNl6xBlx2oK'
    'APu3/kr53i/Dh2QfKYCIXOY1jJ6pnavwhXmGUnGTshcGn3a1MwyWtZxe5GtdgSpeaY3kziMuRUKFowf+4JMGlZJnDeqXdq7A'
    'Z+0Q4d7nZUmJAUamREBVBgLJi/CW6nIiRF43bkcB+Oh2e5NgEHWjXr/lx61O5DX7id8JMC5cOOn5nV6n3R9EzW7UiputdreZ'
    'tPq9waQbJ4Gf9CatjiXovdtpxl2v14wGrUHPi9r90INW/HY/6A66cRR1wkm/E7Q6Xjvxk36nk0RJEiR+szXpJ72g00/24cFA'
    'YVXX6RmhBov401BtVNMObbtbzmayqm8hppM6qzJOLBFcDJIniJgFKx8wS0GlJAQq1QxvzTY9aOXz6bmUgKuFc00+XZyBGEHs'
    '1YMSgDVr/fsz48mtabgUsEbVsrm4sg6Q/d/uelE06RdLFy5CoGQIJXcF7Lom820Tjlz8I5OPwScrC6P3xL34yoZ4VyTiG+kT'
    'IUdxX0o31uBqMqiaZ7rNQ7MqKph1IitoEw+lsquk74f8nKETDxy5V+Juj97iOIpzlKvwVR5/9owc1opG9053zmedC5sXuztm'
    'VoWKiuLZJhCRb/Kbikfxbgo7C+ra4H1uf6GAFGe6wb64TSws98ynRl6C74t1QZ08KYSdEm1Y6U59O4T2bHrw+5OSKFRH06Lo'
    'Sgk95tw0Cjec32s38nZ9vVaJSLIMfMmdKDQgJuL78ot+swXdJED009bonn5/ZbE1OHXUNa69L2WzIktTwIbcsjPpeiTLqABQ'
    'HFFyF41Uq/sC05B4YYp+Ir1FIRSoS0mtTrRktqKf+b1ozzDc/emHCrtADvvQZ+6rHLxXJcyr9+ZC8aoFNlTYhGzMtiwuqYas'
    'kozJfBLOFVph9ptaSVTW/TE0x/JIyU9SS2DIinrmk1wnbKlMhFQvAe8AaTnilsAvHnS1s4NiRCICvRHMVB0+KR98pXTQNbPD'
    '9o1S+o6JU7GZK/Uj/iW78LnNijib+7YrDAOmoMFvASuZrtNNTaY7EYnuDm7b8MczkWpuK8aBvnJIX/ayDCOpnikpaqF4KhiL'
    '5xPGI/kkA/5qEZHcmoYXph/Oy4fR3orxt7i5A0NJUjTemhNH13FNG7sem5fO2a4YeCYV4CdaHm4ZMkTINQ7qo6/tLJkbhevL'
    '+adlgaN0fwSOH/vRrzW9++rbhnoc3FdFxLuq0rWrUJUYprI01wIFp8TGDoyBxx/UjQRQs+c8fOhUBsBNyTBRRFHKLbHZFJBF'
    'prdoCSXDGVUf+mPP8+QfClWzUSAas39s001lACguZLUgR6OsGz84ZEgrKVcnD1pyO4MyM6nkUzraZKEMeOEwZySQ07h3icx1'
    'eDq5z84YhwqHXLAoImQtNhR1wwgFtasnpfkJAYqWmVDNSvGTNWkhrzuaDQNqecY7oY4sz5dIOUoFxWXly/o44nin8tWeVvfn'
    'YDwCmn3kRv9PDUJHixasgzHKmO/w0q5nZfahrVREVeJOtjyOEsGKTeVoS7ZyWPR44A8HB5AvNm2QOTWc7R6WZLqnTrPv7XIM'
    'Q+FAgC6sqpEMaFcGoKJGRBNHYe2z/DZWiFmcCN04mV7kTyzeXS9ptfs7AwqbnMtER/Z6BxOz5sTcy7WYuf1+OTGrh0durdDO'
    'XYZr3rttX8vOmDo57eBEIESKhncXkh3YXUpJYLsK7pPGCsmK8QpJLEt7skCMS//5F0uqPf2GSWvPdq30BfdOMhQJXrbnNBhy'
    'o1YKi4r9HsVcSiK2B4XFsmaz3DOWAjCB93wiXPomcDTMYS3LDfIMi/6IW89LvDaqXKLInz1nd0CPI8wkxMZNcSQS+4iENd/B'
    '4G/i9XQj8xPKHBh0gHgExLiFjx8eybxH18EmVtc/nJhxutASM67WcTK90wgv3a7wLrahyokShZx+6mxIuTOEvH3mfLxX+TDw'
    '4d5ICYlpHUXT1iZlgSpeQl6q9B5AFyuRU4D9m9GORtzqxSqPynaBRiCNclvtXWnoSUV/VDa7vGGCvFg76Bqdc5jSLTpnCdQu'
    '0Ys5nEvu0I1xiQqFu7yRprvMmcirAMMl8YmzFGsHdUoLYZxjY0JTotw2NFglOpVR9fgAv8Ud5SiH2vJccXZHfdXInnx14lX1'
    'N8lKWAAiwvWLAN8UEiHzoBhjnO+qCvRd7MHdCrdKPg6WhBZXlLojvjh2YhdwjOCPVTmGv/Ppk2NG8dfbs8Xxz2vRMgKq5mP7'
    'q7XM2H0kc1SY6zfrW9UihhipNOQEKeIUmpcdLYq0kSbH8N2q7QR/QDokOQO1nXj4bEOsawyPjMYGvBRFfqQST4lDlq6ejuT3'
    '4r95bJYnD7VJVFjiCG907rdMaMzmsNnf1aJ1mZ7IN2d0ldv6glD4NYvQ6DlSO4Y12LjT3lyp94agLXrz1fCgeS6Tr8tImqEf'
    'Ss/Vz7LaKyHmzOBWzQxb1bIQlLem5RB1Rup2M+G6SleRJSI+0+JrHWp9qqfMkkIQ9+uLe2QJsKpbE/O4S4yJ9zaGxw6vtsto'
    'tKons+ZYYibhy4zcGFPX3RESQ1ngGqmkp+mYgiyd2eL4itIggzf4n8qVSJEMIsqV+NPwOugfemTQ49L4GXI4p0MZqEUma645'
    '3U6nZfHOl3xntgwxSfnF5Xl5MI3SDglbftE8hmHzm31r/M49C+mXhcq0zolUxQLC+bU4HvO8TGQmHNG+vUWR00BNuPjVkGHb'
    '8hlPLNM543R/wishc4qeuF+71fL4I6Vo08Wv8nwQDU7rqlItZazL3llUwAylZshqtG4XIFFKJcgWE/QCBUrv3UrhHKZMj1Um'
    '5iuhSTcdyfOpP8ZKRJTm6YfWlxX5CPNehlcw65Jwh3U46zirPUvHl9t1hbKxBHShW7kBEQj9DrRa2i5mx2H9mcCwSqaohlY9'
    'VS/0bmmvjaZO0+0cr/zRvaVWPDVnphYU0Oz547+Oz389f/Hm9dlO3JQs36fbFeUTplWyLVnLxg1tOXGxSZsg5JOd05NZ4sMq'
    'nSYfUKFeqe4UrUrCBh20CHgyKPiQCJtA0cBPjunb/wO1Q3xO')


def frozen_observer_bytes(guest_bytes, causal_bytes):
    """Compose pinned sources; the fail-only hook retains the original entry line."""
    source, causal = guest_bytes.decode('utf-8'), causal_bytes.decode('utf-8')
    require('\r' not in source and '\r' not in causal, 'Observer sources must use LF newlines')
    require(0 < len(causal_bytes) <= 131072, 'Causal source transport bounds differ')
    expected, size, packed = CAUSAL_TRANSPORT
    require(len(causal_bytes) == size and digest(causal_bytes) == expected,
        'Causal source differs from reviewed transport literal')
    require(type(packed) is str and len(packed) <= 131072, 'Compressed source transport bounds differ')
    combined = digest(guest_bytes + b'\0' + causal_bytes)
    return ('#!/usr/bin/env python3\nimport sys, types; _failure={}; '
        f'exec({FAILURE_OBSERVATION_HELPER!r}, _failure); exec({SOURCE_TRANSPORT_HELPER!r}, _failure)\n'
        'causal = types.ModuleType("arctic_performance_causal")\n'
        'causal.__file__ = __file__\n'
        'sys.modules[causal.__name__] = causal\n'
        f'_causal_code=compile(_failure["unpack"]({packed!r}, {len(causal_bytes)}, {digest(causal_bytes)!r}), __file__, "exec"); exec(_causal_code, causal.__dict__)\n'
        'measurement = {"__name__": "arctic_measurement", "__file__": __file__}\n'
        f'_guest_code=compile({source!r}, __file__, "exec"); exec(_guest_code, measurement)\n'
        'if sys.argv[1] == "installed":\n'
        f'    measurement["emit"]("observer_source_sha256", {combined!r}); '
        '_failure["install"]((("causal",_causal_code),("guest",_guest_code)), '
        f'causal.__dict__["StoreProofError"], {combined!r})\n'
        '    measurement["main"](preconditioned=True, causal_precision=True)\n'
        'else:\n'
        '    print("ARCTIC-PERFORMANCE-SKIPPED: live stage; installed comparison only", flush=True)\n').encode()


def observer_hashes_from_sources(guest_bytes, causal_bytes):
    """Reconstruct the pinned composer's exact output, without executing sources."""
    return dict(source_sha256=digest(guest_bytes + b'\0' + causal_bytes),
        frozen_sha256=digest(frozen_observer_bytes(guest_bytes, causal_bytes)))


def observer_hashes(root):
    root = Path(root)
    result = observer_hashes_from_sources((root/'tools/performance/guest.py').read_bytes(),
                                         (root/'tools/performance/causal.py').read_bytes())
    result['comparator_sha256'] = digest((root/'tools/performance/compare.py').read_bytes())
    return result


def validate_plan(plan, *, candidate_source_files, execution_files, observer):
    require(type(plan) is dict and set(plan) == {'schema', 'ready', 'release_acceptance',
        'performance_mode', 'image', 'baseline', 'candidate_source_files', 'observer', 'execution_files'},
        'External paired plan fields differ')
    require(plan['schema'] == 'arctic-external-paired-plan-v1' and type(plan['ready']) is bool
        and plan['release_acceptance'] is False and plan['performance_mode'] == MODE,
        'External paired plan mode/readiness differs')
    image = plan['image']
    require(type(image) is dict and image.get('producer_mode') == MODE
        and re.fullmatch('[0-9a-f]{40}', image.get('source_sha', ''))
        and re.fullmatch('[0-9a-f]{64}', image.get('sha256', ''))
        and re.fullmatch('[0-9a-f]{64}', image.get('producer_receipt_sha256', ''))
        and type(image.get('bytes')) is int and 0 < image['bytes'] < 2_000_000_000,
        'External paired image identity differs')
    require(same(plan['baseline'], BASELINE), 'Immutable original baseline differs')
    for name, declared, actual, keys in (
        ('candidate sources', plan['candidate_source_files'], candidate_source_files, CANDIDATE_SOURCE_FILES),
        ('execution sources', plan['execution_files'], execution_files, EXECUTION_FILES),
        ('observer', plan['observer'], observer, {'source_sha256', 'frozen_sha256', 'comparator_sha256'})):
        require(type(declared) is dict and set(declared) == keys and declared == actual
            and all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) for value in declared.values()),
            'Pinned ' + name + ' differ')
    require(plan['execution_files']['tools/performance/compare.py'] == plan['observer']['comparator_sha256']
        and plan['execution_files']['tools/performance/fixtures/v1.2-offline.toml'] == BASELINE['profile_sha256'],
        'Comparator/baseline profile source pins differ')
    return plan


def parse_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(content, object_pairs_hook=pairs, parse_constant=invalid)


def required_files():
    result = {'status.json', 'comparison.json', 'producer-receipt.json', 'observer-source.txt',
              'vm-base-image-id.txt', 'vm-prepared-image-id.txt'}
    for image in ('baseline', 'candidate'):
        result |= {image + '-install-harness.log', image + '/serial-install.log', image + '/vm-toolchain.txt'}
    for image, boot in ORDER:
        result |= {'runs/' + image + '/' + str(boot) + '/' + name for name in
            ('serial-boot.log', 'harness.log', 'performance-context.json', 'vm-toolchain.txt')}
    return result


def validate_evidence(archive, *, plan, plan_sha256, image, execution_source_sha,
                      reviewed_parent_sha, execution_run_id, comparator, producer_receipt):
    """Verify full original inputs and independently recompute all six boots."""
    validate_plan(plan, candidate_source_files=plan['candidate_source_files'],
        execution_files=plan['execution_files'], observer=plan['observer'])
    require(plan['ready'] is True and same(plan['image'], image), 'Unready/mismatched execution plan')
    for value in (execution_source_sha, reviewed_parent_sha):
        require(type(value) is str and re.fullmatch('[0-9a-f]{40}', value), 'Invalid execution commit')
    require(type(execution_run_id) is int and execution_run_id > 0
        and re.fullmatch('[0-9a-f]{64}', plan_sha256), 'Invalid execution run/plan identity')
    entries = [entry for entry in archive.infolist() if not entry.is_dir()]
    names = [entry.filename for entry in entries]
    require(len(names) == len(set(names)) and len(names) <= 1000
        and sum(entry.file_size for entry in entries) <= 512 * 1024 * 1024, 'Unsafe/oversized paired evidence')
    for entry in entries:
        path = Path(entry.filename)
        require(not path.is_absolute() and '..' not in path.parts
            and (entry.external_attr >> 16 & 0o170000) in (0, 0o100000)
            and path.suffix in {'.json', '.log', '.txt', '.tsv', '.png'}
            and entry.file_size <= 128 * 1024 * 1024, 'Unsafe paired evidence member')
    require(required_files() | {'execution.json', 'upload-screening.json'} <= set(names),
        'Missing full original paired inputs')
    require(0 < archive.getinfo('producer-receipt.json').file_size <= 32_768,
        'Oversized producer receipt member')
    def raw(name):
        return archive.read(name)
    def value(name):
        require(archive.getinfo(name).file_size <= 4 * 1024 * 1024, 'Oversized paired JSON')
        return parse_json(raw(name))
    execution = value('execution.json')
    expected = dict(schema='arctic-external-paired-execution-v1',
        status='frozen_external_paired_regression_gate_passed', release_acceptance=False,
        run_id=execution_run_id, run_attempt=1, execution_source_sha=execution_source_sha,
        reviewed_parent_sha=reviewed_parent_sha, image=image, baseline=BASELINE,
        plan_sha256=plan_sha256, observer=plan['observer'],
        candidate_source_files=plan['candidate_source_files'], execution_files=plan['execution_files'])
    require(set(execution) == set(expected) | {'files'}
        and all(same(execution.get(key), val) for key, val in expected.items()), 'External execution provenance differs')
    files = execution.get('files')
    require(type(files) is dict and set(files) == set(names) - {'execution.json', 'upload-screening.json'},
        'Exact paired input inventory differs')
    screening = value('upload-screening.json')
    require(set(screening.get('files', {})) == set(names) - {'upload-screening.json'}, 'Screening inventory differs')
    for name in set(names) - {'upload-screening.json'}:
        content = raw(name)
        receipt = screening['files'][name]
        require(same(receipt, dict(original_sha256=digest(content), uploaded_sha256=digest(content),
            bytes=len(content), redactions=0)), 'Paired evidence was redacted/truncated: ' + name)
        if name != 'execution.json':
            require(same(files[name], dict(bytes=len(content), sha256=digest(content))), 'Paired input bytes differ: ' + name)
    require(0 < len(raw('producer-receipt.json')) <= 32_768
        and digest(raw('producer-receipt.json')) == image['producer_receipt_sha256']
        and same(value('producer-receipt.json'), producer_receipt), 'Producer receipt bytes differ')
    require(digest(raw('observer-source.txt')) == plan['observer']['frozen_sha256'], 'Frozen observer bytes differ')
    state = value('status.json')
    require(state.get('phase') == 'complete_regression_gate_passed' and state.get('acceleration') == 'kvm'
        and state.get('memory_mib') == 4096 and state.get('vcpus') == 2
        and state.get('restricted_network') is True and state.get('input_images_rechecked') is True
        and state.get('observer_sha256') == plan['observer']['frozen_sha256'], 'Paired host execution differs')
    for key, name in (('vm_base_image_id', 'vm-base-image-id.txt'),
                      ('vm_prepared_image_id', 'vm-prepared-image-id.txt')):
        require(type(state.get(key)) is str and re.fullmatch('(?:sha256:)?[0-9a-f]{64}', state[key])
            and raw(name) == (state[key] + '\n').encode(), 'Immutable VM container identity differs')
    for name, expected_image in (('baseline', BASELINE), ('candidate', image)):
        actual = state.get('images', {}).get(name, {})
        require(same(actual.get('bytes'), expected_image['bytes']) and actual.get('sha256') == expected_image['sha256'],
            'Measured ISO differs: ' + name)
        profile = BASELINE['profile_sha256'] if name == 'baseline' else plan['candidate_source_files']['profiles/ci/offline.toml']
        require(state.get('profiles', {}).get(name, {}).get('sha256') == profile, 'Measured install profile differs')
        require(raw(name + '-install-harness.log').count(b'ARCTIC-PRISTINE-INSTALL-POWEROFF=clean') == 1,
            'Missing/duplicate clean offline installation')
        exits = [line.split(b'ARCTIC-INSTALL-EXIT=', 1)[1].strip()
            for line in raw(name + '/serial-install.log').splitlines() if b'ARCTIC-INSTALL-EXIT=' in line]
        require(exits == [b'0'], 'Missing/duplicate successful offline installation exit')
        pristine = state.get('pristine_installed_sources', {}).get(name, {})
        require(set(pristine) == {'target.qcow2', 'OVMF_VARS.fd'}
            and all(re.fullmatch('[0-9a-f]{64}', val) for val in pristine.values()), 'Missing pristine source identities')
        require(digest(raw(name + '/vm-toolchain.txt')) == state.get('vm_toolchain_sha256'), 'Install toolchain differs')
    require(same(state.get('planned_boot_order'), [dict(image=name, boot=boot) for name, boot in ORDER])
        and same([(row.get('image'), row.get('boot')) for row in state.get('runs', [])], list(ORDER))
        and all(type(row.get('harness_exit')) is int and row['harness_exit'] == 0 for row in state['runs']),
        'Six-boot order/completion differs')
    expected_external = dict(schema='arctic-external-paired-context-v1', run_id=execution_run_id,
        execution_source_sha=execution_source_sha, reviewed_parent_sha=reviewed_parent_sha,
        plan_sha256=plan_sha256, observer=plan['observer'], image_source_sha=image['source_sha'],
        candidate_iso_sha256=image['sha256'])
    runs = dict(baseline=[], candidate=[])
    context_ids = set()
    with tempfile.TemporaryDirectory(prefix='arctic-replay-') as temp:
        for name, boot in ORDER:
            prefix = 'runs/' + name + '/' + str(boot) + '/'
            context = value(prefix + 'performance-context.json')
            require(same(context.get('external_execution'), expected_external)
                and re.fullmatch('[0-9a-f]{32}', context.get('context_id', ''))
                and context['context_id'] not in context_ids, 'Repeated/mismatched external boot context')
            context_ids.add(context['context_id'])
            pristine = state['pristine_installed_sources'][name]
            require(context.get('image') == name and type(context.get('boot')) is int and context['boot'] == boot
                and context.get('collector') == 'console' and context.get('fresh_installed_overlay') is True
                and context.get('installed_base_sha256') == pristine['target.qcow2']
                and context.get('firmware_variables_sha256') == pristine['OVMF_VARS.fd']
                and context.get('iso_sha256') == state['images'][name]['sha256']
                and context.get('install_profile_sha256') == state['profiles'][name]['sha256'], 'Boot source context differs')
            require(digest(raw(prefix + 'vm-toolchain.txt')) == state['vm_toolchain_sha256'], 'Boot toolchain differs')
            log = Path(temp) / (name + '-' + str(boot) + '.log')
            log.write_bytes(raw(prefix + 'serial-boot.log'))
            run = comparator.read_run(log, strict=True)
            require(run.get('observer_source_sha256') == plan['observer']['source_sha256']
                and same(run.get('external_execution'), dict(context=context,
                    observer_file_sha256=plan['observer']['frozen_sha256']))
                and same(run.get('app_roles', {}).get('boot_context'), context),
                'Guest observer/source context differs')
            require(re.fullmatch('[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}',
                run.get('identity', {}).get('boot_id', '')), 'Invalid boot identity')
            runs[name].append(run)
    comparison = comparator.compare_checked(runs, candidate_commit=image['source_sha'][:7],
        candidate_catalog_sha256=plan['candidate_source_files']['shell/AppsService.qml'],
        candidate_battery_sha256=plan['candidate_source_files']['shell/BatteryService.qml'])
    require(same(comparison, value('comparison.json')) and comparison['status'] == 'regression_gate_passed'
        and comparison['measurement_precision']['valid'] is True
        and comparison['measurement_precision']['threshold_enclosure_valid'] is True,
        'Full replay differs or original paired gates failed')
    return dict(performance_mode=MODE, execution_run_id=execution_run_id,
        execution_source_sha=execution_source_sha, image_source_sha=image['source_sha'],
        iso_sha256=image['sha256'], observer=plan['observer'], comparison=comparison,
        original_serials_replayed=6, release_acceptance=False)
