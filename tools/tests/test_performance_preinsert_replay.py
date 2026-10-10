"""Independent replay admission: no GUI, tracefs or measurement publication."""
import copy
import hashlib
import unittest

from tools.tests.test_performance_roles import causal_bound, comparison, paired_roles, receipt


def reseal_bounds(bound):
    proof = bound['causal_lower_bound']
    before = proof.get('matched_events', [])
    after = proof.get('matched_upper_events', [])
    if before and after and all('lower_monotonic_ns' in event for event in before):
        lower = max(proof['ipc_lower_monotonic_ns'], min(event['lower_monotonic_ns'] for event in before))
        upper = min(proof['ipc_upper_monotonic_ns'], min(event['upper_monotonic_ns'] for event in after))
        started = bound['launch_started_monotonic_ns']
        bound.update(lower_seconds=(lower-started)/1e9, upper_seconds=(upper-started)/1e9,
                     interval_seconds=(upper-lower)/1e9)


def reseal_readbacks(proof):
    for record in proof.get('kernel_event_readbacks', {}).values():
        for kind in ('format', 'filter'):
            if kind + '_text' in record:
                record[kind + '_sha256'] = hashlib.sha256(record[kind + '_text'].encode()).hexdigest()


def add_client(bound, branch='head', client_type=2, appid='foot', offset_ns=10_000):
    proof = bound['causal_lower_bound']
    index = len(proof['matched_events'])
    foreign_id = f'{index+1:032x}'
    before_ns = proof['matched_events'][0]['lower_monotonic_ns'] + offset_ns
    after_ns = proof['matched_upper_events'][0]['upper_monotonic_ns'] + offset_ns
    kind = 'xdg' if client_type == 0 else 'x11'
    fields = dict(client_type=client_type, original_app_id=appid, app_id=appid,
                  client_address=0x1000+index*0x100, handle_address=0x2000+index*0x100,
                  handle_owner_address=0x1000+index*0x100)
    identity = receipt('map_create', before_ns-10_000_000)
    before = receipt('map_before_'+branch+'_'+kind, before_ns,
                     instruction_address=proof['lower_executable_mappings'][branch]['instruction_address'], **fields)
    after = receipt('map_listed_'+kind, after_ns, 'upper',
                    instruction_address=proof['upper_instruction_address'], **fields)
    for event in (identity, before, after):
        event['foreign_toplevel_id'] = foreign_id
    proof['matched_identity_events'].append(identity)
    proof['matched_events'].append(before)
    proof['matched_upper_events'].append(after)
    proof['matched_ipc_clients'].append(dict(id=index+1, foreign_toplevel_id=foreign_id, appid=appid))
    reseal_bounds(bound)


class PreinsertReplayTest(unittest.TestCase):
    def reject(self, mutate, appids=('foot',)):
        bound = causal_bound(.03975, .04, appids)
        self.assertTrue(comparison.causal_precision(bound, appids))
        mutate(bound, bound['causal_lower_bound'])
        reseal_readbacks(bound['causal_lower_bound'])
        reseal_bounds(bound)
        self.assertFalse(comparison.causal_precision(bound, appids))

    def test_all_six_branch_types_in_each_exact_whole_elf_profile(self):
        for profile_index in range(3):
            for branch in ('tail', 'head', 'scroller'):
                for client_type in (0, 2):
                    with self.subTest(profile=profile_index, branch=branch, client_type=client_type):
                        bound = causal_bound(.03975, .04, profile_index=profile_index,
                                             branch=branch, client_type=client_type)
                        self.assertTrue(comparison.causal_precision(bound, ('foot',)))
                        self.assertEqual(bound['causal_lower_bound']['upper_mapping_profile']['native_audit_sha256'],
                            'dacb0de958e7ba90099a70b2e66f49756916ed3d42f4e70ac6280f7d4b6a571c')

    def test_multiple_clients_use_any_predicate_and_minimum_native_edges(self):
        bound = causal_bound(.03975, .04, ('foot', 'org.gnome.epiphany'))
        bound['causal_lower_bound']['ipc_lower_monotonic_ns'] = 1_039_690_000
        for index, (branch, kind) in enumerate((('tail', 2), ('head', 0), ('head', 2), ('scroller', 0), ('scroller', 2))):
            add_client(bound, branch, kind, 'org.gnome.epiphany', offset_ns=-10_000*(index+1))
        self.assertTrue(comparison.causal_precision(bound, ('foot', 'org.gnome.epiphany')))
        self.assertEqual(bound['lower_seconds'], .0397)
        self.assertEqual(bound['upper_seconds'], .03995)

    def test_supported_timestamp_resolutions_keep_literal_conservative_edges(self):
        for resolution in (1, 10, 100, 1000):
            bound = causal_bound(.03975, .04)
            proof = bound['causal_lower_bound']
            for key, edge in (('matched_identity_events', 'lower'), ('matched_events', 'lower'), ('matched_upper_events', 'upper')):
                old = proof[key][0]
                fields = {key: value for key, value in old.items() if key not in {
                    'event', 'kernel_pid', 'foreign_toplevel_id', edge+'_monotonic_ns', 'kernel_text_monotonic_ns',
                    'kernel_timestamp_text', 'timestamp_resolution_ns', 'timestamp_rounding_allowance_ns'}}
                proof[key][0] = receipt(old['event'], old[edge+'_monotonic_ns'], edge, resolution, **fields)
            with self.subTest(resolution=resolution):
                self.assertTrue(comparison.causal_precision(bound, ('foot',)))

    def test_original_ipc_negative_and_positive_enclosures_still_intersect(self):
        bound = causal_bound(.03975, .04)
        proof = bound['causal_lower_bound']
        proof['ipc_lower_monotonic_ns'] = 1_039_800_000
        proof['ipc_upper_monotonic_ns'] = 1_039_999_500
        reseal_bounds(bound)
        self.assertTrue(comparison.causal_precision(bound, ('foot',)))
        self.assertEqual(bound['lower_seconds'], .0398)
        self.assertEqual(bound['upper_seconds'], .0399995)

    def test_early_identity_provenance_does_not_widen_native_preinsert_bound(self):
        bound = causal_bound(.03975, .04)
        proof = bound['causal_lower_bound']
        proof['matched_identity_events'][0] = receipt('map_create', 1_000_000_000)
        self.assertTrue(comparison.causal_precision(bound, ('foot',)))
        self.assertEqual(bound['interval_seconds'], .04-.03975)

    def test_old_method_is_rejected_with_otherwise_current_proof(self):
        self.reject(lambda b, p: p.update(method='wlroots-0.20-and-mango-managed-list-original-appid-native-bracket-raw-v4'))

    def test_identity_provenance_is_mandatory(self):
        self.reject(lambda b, p: p.pop('matched_identity_events'))

    def test_wlroots_receipt_cannot_replace_preinsert_native_receipt(self):
        self.reject(lambda b, p: p.update(matched_events=copy.deepcopy(p['matched_identity_events'])))

    def test_each_handle_requires_one_preinsert_receipt(self):
        self.reject(lambda b, p: p['matched_events'].append(copy.deepcopy(p['matched_events'][0])))

    def test_duplicate_handle_cannot_be_hidden_in_parallel_evidence_lists(self):
        def mutate(bound, proof):
            for key in ('matched_identity_events', 'matched_events', 'matched_upper_events', 'matched_ipc_clients'):
                proof[key].append(copy.deepcopy(proof[key][0]))
        self.reject(mutate)

    def test_preinsert_branch_requires_exact_audited_instruction(self):
        self.reject(lambda b, p: p['matched_events'][0].update(event='map_before_head_xdg'))

    def test_preinsert_client_type_and_event_suffix_must_agree(self):
        self.reject(lambda b, p: p['matched_events'][0].update(client_type=2))

    def test_postinsert_client_type_must_be_an_integer(self):
        self.reject(lambda b, p: p['matched_upper_events'][0].update(client_type=False))

    def test_postinsert_event_cannot_change_client_kind(self):
        self.reject(lambda b, p: p['matched_upper_events'][0].update(event='map_listed_x11'))

    def test_identity_must_precede_native_preinsert_edge(self):
        self.reject(lambda b, p: p.update(matched_identity_events=[receipt('map_create', 1_039_751_000)]))

    def test_identity_must_belong_to_the_same_launch(self):
        self.reject(lambda b, p: p.update(matched_identity_events=[receipt('map_create', 999_999_000)]))

    def test_native_preinsert_must_precede_native_postinsert(self):
        def mutate(bound, proof):
            fields = {key: proof['matched_events'][0][key] for key in ('client_type', 'original_app_id', 'app_id',
                'client_address', 'handle_address', 'handle_owner_address', 'instruction_address')}
            proof['matched_events'][0] = receipt('map_before_tail_xdg', 1_040_001_000, **fields)
        self.reject(mutate)

    def test_positive_ipc_receipt_cannot_precede_postinsert_literal(self):
        self.reject(lambda b, p: p.update(ipc_upper_monotonic_ns=1_039_997_000))

    def test_original_ipc_interval_cannot_be_discarded(self):
        self.reject(lambda b, p: p.update(ipc_lower_monotonic_ns=1_040_010_000, ipc_upper_monotonic_ns=1_040_020_000))

    def test_foreign_identifier_must_join_every_evidence_stage(self):
        for key in ('matched_identity_events', 'matched_events', 'matched_upper_events', 'matched_ipc_clients'):
            with self.subTest(stage=key):
                self.reject(lambda b, p: p[key][0].update(foreign_toplevel_id='d'*32))

    def test_original_appid_copy_and_ipc_value_require_literal_equality(self):
        for key in ('original_app_id', 'app_id'):
            with self.subTest(field=key):
                self.reject(lambda b, p: p['matched_events'][0].update(**{key: 'Foot'}))
        self.reject(lambda b, p: p['matched_ipc_clients'][0].update(appid='Foot'))

    def test_matching_original_and_copy_cannot_substitute_an_unrequested_ipc_app(self):
        def mutate(bound, proof):
            for key in ('matched_events', 'matched_upper_events'):
                proof[key][0].update(original_app_id='kitty', app_id='kitty')
            proof['matched_ipc_clients'][0]['appid'] = 'kitty'
        self.reject(mutate)

    def test_bounded_original_appids_reject_string_fault_tokens(self):
        for value in ('(fault)', 'foot\0', 'f'*129, ''):
            def mutate(bound, proof):
                for key in ('matched_events', 'matched_upper_events'):
                    proof[key][0].update(original_app_id=value, app_id=value)
                proof['matched_ipc_clients'][0]['appid'] = value
            with self.subTest(value=repr(value)):
                self.reject(mutate)

    def test_foreign_identifier_alias_cannot_be_an_appid_predicate(self):
        bound = causal_bound(.03975, .04, ('c'*32,))
        self.assertFalse(comparison.causal_precision(bound, ('c'*32,)))

    def test_pre_and_post_native_pointer_identity_must_be_exact(self):
        for key in ('client_address', 'handle_address', 'handle_owner_address'):
            with self.subTest(field=key):
                self.reject(lambda b, p: p['matched_events'][0].update(**{key: 0x5000}))

    def test_owner_must_be_the_client_on_both_native_edges(self):
        def mutate(bound, proof):
            for key in ('matched_events', 'matched_upper_events'):
                proof[key][0]['handle_owner_address'] = 0x3000
        self.reject(mutate)

    def test_client_and_handle_pointers_are_bounded_unsigned_integers(self):
        for value in (0, -1, 2**64, True):
            def mutate(bound, proof):
                for key in ('matched_events', 'matched_upper_events'):
                    proof[key][0]['handle_address'] = value
            with self.subTest(value=value):
                self.reject(mutate)

    def test_per_client_ipc_ids_and_native_pointers_remain_unique(self):
        for field in ('id', 'client_address', 'handle_address'):
            def mutate(bound, proof):
                add_client(bound)
                if field == 'id':
                    proof['matched_ipc_clients'][1][field] = proof['matched_ipc_clients'][0][field]
                else:
                    for key in ('matched_events', 'matched_upper_events'):
                        proof[key][1][field] = proof[key][0][field]
                        if field == 'client_address':
                            proof[key][1]['handle_owner_address'] = proof[key][0][field]
            with self.subTest(field=field):
                self.reject(mutate)

    def test_exact_lower_mapping_branch_inventory_is_required(self):
        self.reject(lambda b, p: p['lower_executable_mappings'].pop('head'))
        self.reject(lambda b, p: p['lower_executable_mappings'].update(extra=copy.deepcopy(p['lower_executable_mappings']['tail'])))

    def test_resealed_guessed_lower_runtime_instruction_is_rejected(self):
        def mutate(bound, proof):
            proof['lower_executable_mappings']['tail']['instruction_address'] += 1
            proof['matched_events'][0]['instruction_address'] += 1
        self.reject(mutate)

    def test_lower_and_upper_mappings_describe_the_same_actual_segment(self):
        def mutate(bound, proof):
            for mapping in proof['lower_executable_mappings'].values():
                mapping.update(start=mapping['start']+0x100000, end=mapping['end']+0x100000,
                               instruction_address=mapping['instruction_address']+0x100000)
            proof['matched_events'][0]['instruction_address'] += 0x100000
        self.reject(mutate)

    def test_exact_audit_pin_cannot_be_resealed_to_an_old_profile(self):
        self.reject(lambda b, p: p['upper_mapping_profile'].update(native_audit_sha256='c263158a0e29ee302bed2f09a24c43e9017ce7d87ceb53d22b86398b39dcd2aa'))

    def test_whole_elf_and_function_pins_remain_mandatory(self):
        for key in ('executable_sha256', 'function_sha256', 'ipc_function_sha256'):
            with self.subTest(pin=key):
                self.reject(lambda b, p: p['upper_mapping_profile'].update(**{key: 'f'*64}))

    def test_boolean_lower_offset_is_not_an_audited_machine_offset(self):
        self.reject(lambda b, p: p['upper_mapping_profile']['lower_instruction_file_offsets'].update(tail=True))

    def test_resealed_kernel_timestamp_literal_and_edge_still_must_agree(self):
        for key in ('matched_identity_events', 'matched_events', 'matched_upper_events'):
            with self.subTest(stage=key):
                self.reject(lambda b, p: p[key][0].update(kernel_timestamp_text='1.000001'))

    def test_coarse_kernel_timestamps_remain_unqualified(self):
        def mutate(bound, proof):
            before = proof['matched_events'][0]
            fields = {key: before[key] for key in ('client_type', 'original_app_id', 'app_id',
                'client_address', 'handle_address', 'handle_owner_address', 'instruction_address')}
            proof['matched_events'][0] = receipt('map_before_tail_xdg', 1_039_750_000, resolution=10_000, **fields)
        self.reject(mutate)

    def test_kernel_pid_uid_start_ticks_and_raw_clock_cannot_be_relaxed(self):
        for field, value in (('kernel_pid', True), ('desktop_uid', 0), ('mango_start_ticks', -1),
                             ('clock', 'mono'), ('userspace_clock', 'CLOCK_MONOTONIC')):
            with self.subTest(field=field):
                self.reject(lambda b, p: p.update(**{field: value}))
        self.reject(lambda b, p: b.update(clock='CLOCK_MONOTONIC'))

    def test_each_native_edge_requires_the_proven_kernel_pid(self):
        for key in ('matched_identity_events', 'matched_events', 'matched_upper_events'):
            with self.subTest(stage=key):
                self.reject(lambda b, p: p[key][0].update(kernel_pid=124))

    def test_loss_and_incomplete_loss_inventory_remain_fail_closed(self):
        for field in ('overrun', 'commit overrun', 'dropped events'):
            with self.subTest(field=field):
                self.reject(lambda b, p: p['loss_counts']['cpu0'].update(**{field: 1}))
        self.reject(lambda b, p: p.update(loss_counts={}))

    def test_kernel_readbacks_are_mandatory_and_have_exact_nine_names(self):
        self.reject(lambda b, p: p.pop('kernel_event_readbacks'))
        self.reject(lambda b, p: p['kernel_event_readbacks'].pop('map_before_head_x11'))
        self.reject(lambda b, p: p['kernel_event_readbacks'].update(unknown=copy.deepcopy(p['kernel_event_readbacks']['map_create'])))

    def test_kernel_readback_records_have_exact_four_literal_fields(self):
        self.reject(lambda b, p: p['kernel_event_readbacks']['map_create'].update(expected_filter='common_pid == 123'))
        self.reject(lambda b, p: p['kernel_event_readbacks']['map_create'].pop('format_text'))

    def test_resealed_kernel_formats_reject_field_inventory_order_types_and_offsets(self):
        mutations = [
            ('field:u32 client_type;', 'field:u64 client_type;'),
            ('field:__data_loc char[] original_app_id;', 'field:__data_loc char[] other_id;'),
            ('offset:20;', 'offset:24;'), ('size:4;', 'size:8;'), ('signed:1;', 'signed:0;'),
            ('field:u64 client;', 'field:x64 client;'),
            ('field:int common_pid;', 'field:unsigned int common_pid;'),
        ]
        for old, new in mutations:
            def mutate(bound, proof):
                record = proof['kernel_event_readbacks']['map_before_tail_xdg']
                record['format_text'] = record['format_text'].replace(old, new, 1)
            with self.subTest(old=old, new=new):
                self.reject(mutate)
        def reorder(bound, proof):
            record = proof['kernel_event_readbacks']['map_create']
            lines = record['format_text'].splitlines(keepends=True)
            lines[3], lines[4] = lines[4], lines[3]
            record['format_text'] = ''.join(lines)
        self.reject(reorder)

    def test_resealed_kernel_format_name_id_and_footer_are_validated(self):
        for old, new in (('name: map_create', 'name: map_listed_xdg'), ('ID: 100', 'ID: 101'),
                         ('ID: 100', 'ID: 65536'), ('ID: 100', 'ID: 0'),
                         ('__get_str(foreign_id)', 'REC->foreign_id')):
            def mutate(bound, proof):
                record = proof['kernel_event_readbacks']['map_create']
                record['format_text'] = record['format_text'].replace(old, new, 1)
            with self.subTest(old=old, new=new):
                self.reject(mutate)
        self.reject(lambda b, p: p['kernel_event_readbacks']['map_create'].update(
            format_text=p['kernel_event_readbacks']['map_create']['format_text']+'\n'))

    def test_resealed_kernel_readback_text_is_bounded_ascii_and_lf_only(self):
        for field, value in (('format_text', 'x'*16385+'\n'), ('filter_text', ' '*1025+'\n'),
                             ('filter_text', 'common_pid == 123\r\n'), ('filter_text', 'common_pid == 123\0\n'),
                             ('filter_text', 'common_pid == 123é\n')):
            with self.subTest(field=field, value=repr(value[:50])):
                self.reject(lambda b, p: p['kernel_event_readbacks']['map_create'].update(**{field: value}))

    def test_kernel_readback_digest_covers_literal_text_not_normalized_text(self):
        bound = causal_bound(.03975, .04)
        record = bound['causal_lower_bound']['kernel_event_readbacks']['map_create']
        record['filter_text'] = record['filter_text'].replace(' == ', '==')
        self.assertFalse(comparison.causal_precision(bound, ('foot',)))
        reseal_readbacks(bound['causal_lower_bound'])
        self.assertTrue(comparison.causal_precision(bound, ('foot',)))

    def test_resealed_effective_kernel_filters_reject_missing_or_extra_predicates(self):
        for value in ('none\n', 'common_pid == 124\n', 'common_pid == 123 && client_type == 2\n',
                      'common_pid == 123 || client_type == 0\n', 'common_pid == 123 && client_type == 0 && 1 == 1\n',
                      '(common_pid == 123) && client_type == 0\n', 'common_\npid == 123 && client_type == 0\n',
                      'common_pid = = 123 && client_type == 0\n'):
            with self.subTest(value=value):
                self.reject(lambda b, p: p['kernel_event_readbacks']['map_before_tail_xdg'].update(filter_text=value))

    def test_wide_native_cold_bracket_still_fails_unchanged_numeric_gate(self):
        runs = paired_roles()
        timing = runs['candidate'][0]['startup_role_terminal_cold_seconds']
        timing['observation_bounds'] = [causal_bound(.0389, .04)]
        result = comparison.compare(runs)
        check = result['measurement_precision']['checks']['candidate'][0][0]
        self.assertTrue(check['causal_lower_bound_valid'])
        self.assertEqual(check['maximum_interval_seconds'], .001)
        self.assertFalse(check['valid'])
        self.assertEqual(result['status'], 'measurement_precision_gate_failed')
        self.assertFalse(any(row['regression'] for row in result['metrics']))
        self.assertEqual(next(row for row in result['metrics'] if row['metric']=='terminal_first_gui_role_mapped')['regression_threshold_percent'], 10)


if __name__ == '__main__':
    unittest.main()
