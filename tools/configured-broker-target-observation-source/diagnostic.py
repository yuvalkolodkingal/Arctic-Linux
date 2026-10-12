"""Default-off fixed configured-Source-target diagnostic; never privacy admission."""
import re,types
TARGETS=(('org.freedesktop.portal.Desktop','configured-source-target-001'),('org.a11y.Bus','configured-source-target-002'),('org.a11y.atspi.Registry','configured-source-target-003'))
FACTORY=re.compile(r'1\.(?P<unique>0|[1-9][0-9]{0,19})-(?P<name>'+ '|'.join(re.escape(name)for name,_ in TARGETS)+r')@(?P<instance>0|[1-9][0-9]{0,19})\.service')
UINT64_MAX=18446744073709551615

def diagnostic_configured_factory(scanner,helper,match,phase,original=None,boundaries=None,removed=None,*,enabled=False):
    """Caller binds exact scanner/helper Source and same owned rejection frame.

    This pure function uses the already-held original buffer and original Match.
    It acquires nothing. Future adapter must authenticate existing Source owners
    before/after this optional call; output never proves executed code or cause.
    """
    result={'schema':'arctic-configured-broker-target-source-diagnostic-v1','target_id':'unknown','exact_configured_factory_shape':False,'privacy_admitted':False,'runtime_cause_proven':False,'operand_value_or_digest_exported':False}
    if type(enabled)is not bool or not enabled:return result
    if(type(scanner)is not types.ModuleType or type(helper)is not types.ModuleType or type(match)is not re.Match
       or type(phase)is not str or phase!='source-view' or match.re is not scanner.EXTERNAL_SENSITIVE
       or not 0<match.end()-match.start()<=256):return result
    aligned=helper.diagnostic_view_alignment(scanner,match,phase,original,boundaries,removed)
    if aligned!={'regex':'exact-scanner-regex','offsets':'exact-scanner-span','mapping':'exact-source-view'}:return result
    value=match.group(0);factory=FACTORY.fullmatch(value)
    if factory is None or int(factory.group('unique'))>=UINT64_MAX or int(factory.group('instance'))>UINT64_MAX:return result
    first,last=scanner.original_span(match.start(),match.end(),boundaries,removed)
    if(type(first)is not int or type(last)is not int or not 6<=first<=last<=len(original)
       or last-first!=len(value) or original[first:last]!=value or original[first-6:first]!='dbus-:'):return result
    start=first-6;delimiters=' \t\r\n:'
    if(start!=0 and original[start-1]not in delimiters)or(last!=len(original)and original[last]not in delimiters):return result
    result['target_id']=dict(TARGETS)[factory.group('name')];result['exact_configured_factory_shape']=True
    return result
