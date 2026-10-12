"""Default-off same-rejection member and whole-record-family diagnostic."""
import re,types

XDG_AUTOSTART=re.compile(r'app-[A-Za-z0-9_.:-]{1,192}@autostart\.service')
UNIT_FAMILY_IDS=('unknown','repo-xdg-autostart-unit')
SOURCE_MEMBER_IDS=('unknown','serial-install-log','serial-boot-log')
RECORD_FAMILY_IDS=(
    'unknown',
    'systemd-kernel-lifecycle',
    'systemd-job-lifecycle',
    'systemd-kernel-deactivated',
    'systemd-install-masked',
    'systemctl-user-failed-row',
)
JOB_PREFIX=r'(?:\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d+Z )?'
KERNEL_PREFIX=JOB_PREFIX+r'\[ *\d+\.\d+\] systemd\[1\]: '
DESCRIPTION=r'[^\x00-\x1f\x7f]{1,512}'
STATES=(
    r'(?:loaded|not-found|masked) +'
    r'(?:active|inactive|failed|activating|deactivating|reloading) +'
    r'(?:running|exited|dead|failed|start-pre|start|start-post|reload|stop|stop-sigterm|stop-sigkill|stop-post|final|auto-restart)'
)

def diagnostic_unit_record_family(scanner,helper,match,phase,original=None,boundaries=None,removed=None,
                                  *,stage='unknown',enabled=False):
    """Return only fixed member/family IDs and booleans from one rejected Match."""
    result={'schema':'arctic-unit-record-family-source-diagnostic-v1',
        'source_member_id':'unknown','unit_family_id':'unknown','record_family_id':'unknown',
        'exact_repo_attested_unit_family':False,'exact_repo_attested_record_family':False,
        'privacy_admitted':False,'runtime_cause_proven':False,
        'operand_value_or_digest_exported':False,'release_acceptance':False}
    if type(enabled)is not bool or not enabled:return result
    if(type(scanner)is not types.ModuleType or type(helper)is not types.ModuleType
       or type(match)is not re.Match or type(phase)is not str or phase!='source-view'
       or type(stage)is not str or stage not in('live','installed')
       or match.re is not scanner.EXTERNAL_SENSITIVE or not 0<match.end()-match.start()<=256):return result
    aligned=helper.diagnostic_view_alignment(scanner,match,phase,original,boundaries,removed)
    if aligned!={'regex':'exact-scanner-regex','offsets':'exact-scanner-span','mapping':'exact-source-view'}:return result
    first,last=scanner.original_span(match.start(),match.end(),boundaries,removed)
    delimiters=' \t\r\n:'
    if(type(first)is not int or type(last)is not int or not 0<=first<last<=len(original)
       or last-first!=match.end()-match.start() or original[first:last]!=match.group(0)
       or (match.start()!=0 and match.string[match.start()-1]not in delimiters)
       or (match.end()!=len(match.string) and match.string[match.end()]not in delimiters)):return result
    result['source_member_id']='serial-install-log' if stage=='live' else 'serial-boot-log'
    if XDG_AUTOSTART.fullmatch(match.group(0)) is None:return result
    result['unit_family_id']='repo-xdg-autostart-unit'
    result['exact_repo_attested_unit_family']=True

    left=max(match.string.rfind('\n',0,match.start()),match.string.rfind('\r',0,match.start()))+1
    ends=[n for n in(match.string.find('\n',match.end()),match.string.find('\r',match.end()))if n>=0]
    right=min(ends)if ends else len(match.string)
    if not 0<=left<=match.start()<match.end()<=right<=len(match.string) or right-left>4096:return result
    record=match.string[left:right]
    relative=match.start()-left
    if record[relative:relative+match.end()-match.start()]!=match.group(0):return result
    unit=re.escape(match.group(0))
    lifecycle=(r'(?:Starting|Stopping) '+unit+r' - '+DESCRIPTION+r'\.\.\.'
               r'|(?:Started|Finished|Stopped) '+unit+r' - '+DESCRIPTION+r'\.')
    families=(
        ('systemd-kernel-lifecycle',KERNEL_PREFIX+r'(?:'+lifecycle+r')'),
        ('systemd-job-lifecycle',JOB_PREFIX+r'(?:\[  OK  \] | {9})(?:'+lifecycle+r')'),
        ('systemd-kernel-deactivated',KERNEL_PREFIX+unit+r': Deactivated successfully\.'),
        ('systemd-install-masked',r'Unit '+unit+r' is masked, ignoring\.'),
        ('systemctl-user-failed-row',
         r'(?:● +)?'+unit+r' +'+STATES+r' +'+DESCRIPTION),
    )
    matched=[identifier for identifier,pattern in families if re.fullmatch(pattern,record)is not None]
    if len(matched)==1:
        result['record_family_id']=matched[0]
        result['exact_repo_attested_record_family']=True
    return result
