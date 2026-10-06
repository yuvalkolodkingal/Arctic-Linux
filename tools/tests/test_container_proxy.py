"""Build containers honor the caller's independent HTTP/HTTPS proxy choices."""
from pathlib import Path
import os
import subprocess
import unittest

HELPER = Path(__file__).parents[1]/'lib/container.sh'


class ContainerProxyTest(unittest.TestCase):
    def arguments(self, **proxy):
        env = {key: value for key, value in os.environ.items()
               if key.lower() not in ('http_proxy', 'https_proxy', 'no_proxy')}
        env.update(proxy, ARCTIC_CA_BUNDLE='/nonexistent-test-ca')
        result = subprocess.check_output(
            ['bash', '-c', 'source "$1"; arctic_container_args; '
             'if (( ${#ARCTIC_CONTAINER_ARGS[@]} )); then printf "%s\\0" "${ARCTIC_CONTAINER_ARGS[@]}"; fi',
             'proxy-test', str(HELPER)], env=env)
        return result.decode().rstrip('\0').split('\0') if result else []

    def test_http_only_and_https_only_are_independent(self):
        http = self.arguments(HTTP_PROXY='http://http.example:8080')
        https = self.arguments(https_proxy='http://https.example:8080')
        self.assertIn('HTTP_PROXY=http://http.example:8080', http)
        self.assertNotIn('HTTPS_PROXY=http://http.example:8080', http)
        self.assertIn('HTTPS_PROXY=http://https.example:8080', https)
        self.assertNotIn('HTTP_PROXY=http://https.example:8080', https)
        self.assertEqual(http[:2], ['--network', 'host'])
        self.assertEqual(https[:2], ['--network', 'host'])

    def test_distinct_proxy_and_bypass_values_are_preserved(self):
        args = self.arguments(HTTP_PROXY='http://http.example:8080',
                              HTTPS_PROXY='http://https.example:8080', NO_PROXY='localhost,.example')
        for value in ('HTTP_PROXY=http://http.example:8080',
                      'HTTPS_PROXY=http://https.example:8080', 'NO_PROXY=localhost,.example'):
            self.assertIn(value, args)

    def test_without_a_proxy_no_network_override_is_added(self):
        self.assertEqual(self.arguments(), [])
