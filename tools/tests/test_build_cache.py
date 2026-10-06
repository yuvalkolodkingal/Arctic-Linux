"""Native dependency invalidation and builder/source cache boundaries."""
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('build_cache', Path(__file__).parents[1]/'build-cache.py')
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)


class NativeCacheIdentityTest(unittest.TestCase):
    image = 'sha256:' + 'a'*64
    inventory = 'golang\tgolang-1.27.1-1.fc44.x86_64\ngtk4\tgtk4-4.20.0-1.fc44.x86_64\nmangowm\tmangowm-0.13.2-1.preview.fc44.x86_64\n'

    def test_native_library_release_or_builder_change_invalidates_cgo_cache(self):
        original = cache.manifest(self.image, self.inventory)['cache_key']
        changed = self.inventory.replace('gtk4-4.20.0-1.', 'gtk4-4.20.0-2.')
        self.assertNotEqual(original, cache.manifest(self.image, changed)['cache_key'])
        self.assertNotEqual(original, cache.manifest('b'*64, self.inventory)['cache_key'])
        self.assertNotEqual(original, cache.manifest(self.image, self.inventory +
            'arctic-native-lib\tarctic-native-lib-1.0-1.fc44.x86_64\n')['cache_key'])

    def test_project_release_and_inventory_order_do_not_discard_valid_compilation(self):
        changed = self.inventory.replace('1.preview', '2.preview')
        changed = '\n'.join(reversed(changed.splitlines())) + '\n'
        self.assertEqual(cache.manifest(self.image, self.inventory)['cache_key'],
                         cache.manifest(self.image, changed)['cache_key'])

    def test_unknown_builder_empty_or_malformed_inventory_is_rejected(self):
        for image, inventory in [('fedora:44', self.inventory), (self.image, ''),
                                 (self.image, 'gtk4 without NEVRA')]:
            with self.subTest(image=image, inventory=inventory), self.assertRaises(ValueError):
                cache.manifest(image, inventory)
