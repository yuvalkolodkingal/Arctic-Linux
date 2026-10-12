"""Default-off same-rejection broker factory shape diagnostic; never privacy admission."""
import re,types
TARGETS=(
    ('org.freedesktop.portal.Desktop','broker-source-target-001'),
    ('org.a11y.Bus','broker-source-target-002'),
    ('org.a11y.atspi.Registry','broker-source-target-003'),
    ('org.freedesktop.Notifications','broker-source-target-004'),
    ('org.freedesktop.ScreenSaver','broker-source-target-005'),
    ('org.freedesktop.UPower','broker-source-target-006'),
    ('org.freedesktop.PolicyKit1','broker-source-target-007'),
    ('org.freedesktop.NetworkManager','broker-source-target-008'),
    ('org.freedesktop.UPower.PowerProfiles','broker-source-target-009'),
    ('org.freedesktop.DBus','broker-source-target-010'),
)
BUS_NAME=r'(?:[A-Za-z_][A-Za-z0-9_-]*\.)+[A-Za-z_][A-Za-z0-9_-]*'
FACTORY=re.compile(r'1\.(?P<unique>0|[1-9][0-9]{0,19})-(?P<name>'+BUS_NAME+r')@(?P<instance>0|[1-9][0-9]{0,19})\.service')
UINT64_MAX=18446744073709551615

def diagnostic_broker_factory_shape(scanner,helper,match,phase,original=None,boundaries=None,removed=None,*,enabled=False):
    """Return one generic shape boolean and one closed repo-attested public ID.

    The caller binds the exact scanner/helper and same owned rejection frame.
    This pure function reads only the already-held original string and Match.
    It performs no IO and exports no operand, digest, numeric field or length.
    """
    result={'schema':'arctic-broker-factory-shape-source-diagnostic-v1',
        'target_id':'unknown','exact_broker_factory_shape':False,
        'privacy_admitted':False,'runtime_cause_proven':False,
        'operand_value_or_digest_exported':False,'release_acceptance':False}
    if type(enabled)is not bool or not enabled:return result
    if(type(scanner)is not types.ModuleType or type(helper)is not types.ModuleType
       or type(match)is not re.Match or type(phase)is not str or phase!='source-view'
       or match.re is not scanner.EXTERNAL_SENSITIVE or not 0<match.end()-match.start()<=256):return result
    aligned=helper.diagnostic_view_alignment(scanner,match,phase,original,boundaries,removed)
    if aligned!={'regex':'exact-scanner-regex','offsets':'exact-scanner-span','mapping':'exact-source-view'}:return result
    factory=FACTORY.fullmatch(match.group(0))
    if factory is None or int(factory.group('unique'))>=UINT64_MAX or int(factory.group('instance'))>UINT64_MAX:return result
    first,last=scanner.original_span(match.start(),match.end(),boundaries,removed)
    if(type(first)is not int or type(last)is not int or not 6<=first<=last<=len(original)
       or last-first!=match.end()-match.start() or original[first:last]!=match.group(0)
       or original[first-6:first]!='dbus-:'):return result
    start=first-6;delimiters=' \t\r\n:'
    if(start!=0 and original[start-1]not in delimiters)or(last!=len(original)and original[last]not in delimiters):return result
    result['exact_broker_factory_shape']=True
    result['target_id']=dict(TARGETS).get(factory.group('name'),'unknown')
    return result
