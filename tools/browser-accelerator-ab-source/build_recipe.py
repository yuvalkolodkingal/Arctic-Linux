"""Plan-only hosted A/B build inputs. This module never executes a build."""
import hashlib
import re

SRPM = dict(name='epiphany-50.6-1.fc44.src.rpm', bytes=4603759,
    sha256='f8ad7e58f40a0be422649a7e197854cee076b0168bcf09cea033747307d3d89a')
MEMBERS = {
    'epiphany.spec': (8598, '4e0f87ba947c53bc463d2f6ee38aee592c69b89f6a17f228a64f33c19bc18d51'),
    'epiphany-50.6.tar.xz': (4577640, '458222a8694cfc914e7a2d6de9879067001a8d65e00a907d96112059c67ad446'),
    'epiphany-default-bookmarks.patch': (1753, '62ae5bc0477cf5b0b3bc7908d1829d512cd85c098f4285f651eda7981499c1d7'),
}
FINGERPRINT = '36F612DCF27F7D1A48A835E4DBFCF71C6D9F90A6'
TOPDIR = '/build/rpmbuild'


def build_plan(container_digest, dependency_census_sha256, macro_census_sha256,
               srpm_raw, spec_raw, window_raw, patch_raw, candidate):
    """Require concrete hosted producer inputs; return fixed argv, not shell code.

    A future host runner must verify signed SRPM and all member bytes before
    preparation. Dependency and macro censuses cannot be substituted by guessed
    image package versions. Neither a tag nor an unbound snapshot is admitted.
    """
    if not re.fullmatch(r'registry\.fedoraproject\.org/fedora@sha256:[0-9a-f]{64}', container_digest):
        raise RuntimeError('build_container_binding')
    if not all(re.fullmatch(r'[0-9a-f]{64}', x) for x in (dependency_census_sha256, macro_census_sha256)):
        raise RuntimeError('build_toolchain_binding')
    if len(srpm_raw) != SRPM['bytes'] or hashlib.sha256(srpm_raw).hexdigest() != SRPM['sha256']:
        raise RuntimeError('build_source_binding')
    if len(spec_raw) != MEMBERS['epiphany.spec'][0] or hashlib.sha256(spec_raw).hexdigest() != MEMBERS['epiphany.spec'][1]:
        raise RuntimeError('build_spec_binding')
    if not patch_raw or len(patch_raw) > 32768 or patch_raw != candidate.window_patch(window_raw):
        raise RuntimeError('build_patch_binding')
    # Applying the exact reviewed Source patch and its whole inverse is a
    # producer prerequisite, not an arbitrary caller-controlled patch flag.
    patched_spec = candidate.candidate_spec(spec_raw)
    return dict(schema='arctic-disabled-epiphany-accelerator-ab-build-v1', ready=False,
        container=container_digest, target='x86_64', topdir=TOPDIR,
        source=SRPM, signed_by=FINGERPRINT,
        dependency_census_sha256=dependency_census_sha256,
        macro_census_sha256=macro_census_sha256,
        baseline_spec_sha256=hashlib.sha256(spec_raw).hexdigest(),
        candidate_spec_sha256=hashlib.sha256(patched_spec).hexdigest(),
        candidate_patch_sha256=hashlib.sha256(patch_raw).hexdigest(),
        runs=[dict(variant=v, argv=['rpmbuild', '-bb', '--target', 'x86_64',
                  '--define', '_topdir '+TOPDIR, TOPDIR+'/SPECS/epiphany.spec'],
                  clean_same_topdir_before=True, full_checks=True)
              for v in ('baseline', 'candidate')],
        install_payload=False, VM_runs=0, performance_acceptance=False,
        required_producer_evidence=['whole_signed_SRPM', 'all_Source_member_SHA256',
            'whole_prepared_Source_tree_inverse', 'resolved_dependency_census',
            'whole_macro_census', 'container_digest', 'both_original_build_logs',
            'both_runtime_RPMs', 'both_whole_libephymain_ELFs', 'both_BuildIDs',
            'both_debuglink_CRC_and_debug_ELFs', 'both_dependency_ABIs'],
        runtime_overlay_ready=False)
