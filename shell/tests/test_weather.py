"""Tests for shell/scripts/weather.py: the request it makes (rounded coordinates, units), the
reading's shape, the cache, offline answers, the place (chosen or from the time zone) and the
place search, against a local stand-in for Open-Meteo.

Run: python3 -m unittest discover -s shell/tests
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).parents[2]
SCRIPT = REPO / 'shell' / 'scripts' / 'weather.py'
ZONE1970 = '#codes\tcoordinates\tTZ\tcomments\nIL\t+314650+0351326\tAsia/Jerusalem\nUS\t+404251-0740023\tAmerica/New_York\n'
FORECAST = {
    'current': {'temperature_2m': 21.44, 'apparent_temperature': 22.0, 'weather_code': 2, 'is_day': 1, 'wind_speed_10m': 12.3},
    'daily': {'time': ['2026-09-28', '2026-09-29'], 'weather_code': [3, 61], 'temperature_2m_max': [27.4, 25.0],
              'temperature_2m_min': [19.2, 18.0], 'precipitation_probability_max': [10, 80],
              'sunrise': ['2026-09-28T06:32', '2026-09-29T06:33'], 'sunset': ['2026-09-28T18:24', '2026-09-29T18:23']},
}
PLACES = {'results': [{'name': 'Haifa', 'latitude': 32.81841, 'longitude': 34.9885, 'admin1': 'Haifa District', 'country': 'Israel'},
                      {'name': 'Nowhere', 'latitude': 123, 'longitude': 0}]}


class Server(BaseHTTPRequestHandler):
    requests = []
    down = False

    def do_GET(self):  # noqa: N802
        Server.requests.append((self.path, self.headers.get('User-Agent')))
        if Server.down:
            self.send_response(503)
            self.end_headers()
            return
        body = json.dumps(PLACES if self.path.startswith('/v1/search') else FORECAST).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class WeatherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), Server)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = 'http://127.0.0.1:{}'.format(cls.server.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Server.requests.clear()
        Server.down = False
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / 'zoneinfo').mkdir()
        (root / 'zoneinfo' / 'zone1970.tab').write_text(ZONE1970)
        self.config = root / 'config' / 'arctic'
        self.config.mkdir(parents=True)
        self.env = {k: v for k, v in os.environ.items() if 'proxy' not in k.lower()}
        self.env.update(HOME=str(root), XDG_CONFIG_HOME=str(root / 'config'), XDG_CACHE_HOME=str(root / 'cache'),
                        ARCTIC_ZONEINFO=str(root / 'zoneinfo'), ARCTIC_TIMEZONE='Asia/Jerusalem', LANG='he_IL.UTF-8',
                        ARCTIC_WEATHER_API=self.base + '/v1/forecast', ARCTIC_GEOCODE_API=self.base + '/v1/search',
                        PYTHONDONTWRITEBYTECODE='1')
        self.env.pop('LC_ALL', None)
        self.env.pop('LC_MEASUREMENT', None)

    def tearDown(self):
        self.tmp.cleanup()

    def weather(self, *args, code=0):
        out = subprocess.run([sys.executable, str(SCRIPT)] + list(args) + ['--json'], env=self.env,
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, code, out.stdout + out.stderr)
        return json.loads(out.stdout)

    def test_the_request_and_the_reading(self):
        data = self.weather('now')
        path, agent = Server.requests[0]
        query = parse_qs(urlparse(path).query)
        self.assertEqual((query['latitude'], query['longitude']), (['31.78'], ['35.22']))    # about 1 km
        self.assertEqual((query['temperature_unit'], query['wind_speed_unit']), (['celsius'], ['kmh']))
        self.assertEqual((query['timezone'], query['forecast_days']), (['auto'], ['5']))
        self.assertIn('Arctic-Linux', agent)
        self.assertEqual((data['place'], data['source'], data['units'], data['attribution']),
                         ('Jerusalem', 'zone', 'metric', 'Open-Meteo.com'))
        self.assertEqual(data['current'], {'temp': 21.4, 'feels': 22.0, 'code': 2, 'is_day': True, 'wind': 12})
        self.assertEqual(data['daily'][1], {'date': '2026-09-29', 'code': 61, 'max': 25, 'min': 18, 'rain': 80,
                                            'sunrise': '06:33', 'sunset': '18:23'})

    def test_the_cache_and_offline(self):
        self.weather('now')
        self.assertTrue(self.weather('now')['cached'])
        self.assertEqual(len(Server.requests), 1)                          # fresh: no second request
        Server.down = True
        data = self.weather('now', '--max-age', '0', code=1)
        self.assertEqual(data['code'], 'service')
        self.assertEqual(data['cached']['current']['code'], 2)             # the last reading, to show
        self.env['ARCTIC_WEATHER_API'] = 'http://127.0.0.1:9/v1/forecast'  # nothing listens there
        self.assertEqual(self.weather('now', '--max-age', '0', code=1)['code'], 'offline')

    def test_units(self):
        self.env['LANG'] = 'en_US.UTF-8'
        self.assertEqual(self.weather('now')['units'], 'imperial')
        query = parse_qs(urlparse(Server.requests[-1][0]).query)
        self.assertEqual((query['temperature_unit'], query['wind_speed_unit']), (['fahrenheit'], ['mph']))
        self.assertEqual(self.weather('now', '--units', 'metric')['units'], 'metric')
        self.assertEqual(len(Server.requests), 2, 'other units: a new request, not the cache')

    def test_places(self):
        (self.config / 'location.json').write_text(json.dumps({'name': 'Haifa', 'detail': 'Israel', 'lat': 32.8184, 'lon': 34.9885}))
        self.assertEqual(self.weather('place')['source'], 'chosen')
        self.assertEqual(self.weather('now')['place'], 'Haifa')
        query = parse_qs(urlparse(Server.requests[-1][0]).query)
        self.assertEqual(query['latitude'], ['32.82'])
        (self.config / 'location.json').write_text('{"name": "Bad", "lat": 99, "lon": 0}')
        self.assertEqual(self.weather('place')['source'], 'zone')           # a bad file is ignored
        self.env['ARCTIC_TIMEZONE'] = 'Mars/Olympus'
        self.assertEqual(self.weather('now', code=1)['code'], 'no_location')

    def test_geocode(self):
        data = self.weather('geocode', 'Haifa', '--lang', 'he')
        self.assertEqual(data['places'], [{'name': 'Haifa', 'detail': 'Haifa District, Israel', 'lat': 32.8184, 'lon': 34.9885}])
        query = parse_qs(urlparse(Server.requests[-1][0]).query)
        self.assertEqual((query['name'], query['language'], query['count']), (['Haifa'], ['he'], ['6']))
        self.assertEqual(self.weather('geocode', 'x', code=1)['code'], 'usage')


if __name__ == '__main__':
    unittest.main()
