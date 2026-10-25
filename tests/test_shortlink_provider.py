"""Unit tests for provider-aware short-link handling without live API calls."""
import ast
import asyncio
import json
import logging
import re
import unittest
from pathlib import Path
from urllib.parse import urlparse


class FakeResponse:
    def __init__(self, status=200, body='{}', content_type='application/json'):
        self.status = status
        self._body = body
        self.headers = {'Content-Type': content_type}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def text(self):
        return self._body

    async def json(self, content_type=None):
        return json.loads(self._body)


class FakeSession:
    response = FakeResponse()
    last_url = None
    last_params = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def get(self, url, params=None, headers=None):
        type(self).last_url = url
        type(self).last_params = params
        return type(self).response


class FakeClientTimeout:
    def __init__(self, **kwargs):
        pass


class FakeAiohttp:
    ClientTimeout = FakeClientTimeout
    ClientSession = FakeSession
    class ContentTypeError(Exception):
        pass


class FakeShortzy:
    def __init__(self, api, site):
        self.api, self.site = api, site

    async def convert(self, link):
        if self.site == 'convert-fails.test':
            raise RuntimeError('conversion unavailable')
        return 'https://short.example/converted'

    async def get_quick_link(self, link):
        return 'https://short.example/quick'


def load_provider_functions():
    source = (Path(__file__).resolve().parents[1] / 'utils.py').read_text()
    tree = ast.parse(source)
    wanted = {'normalize_shortener_domain', 'create_shortlink', 'get_shortlink'}
    nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in wanted]
    namespace = {
        're': re, 'asyncio': asyncio, 'aiohttp': FakeAiohttp,
        'Shortzy': FakeShortzy, 'logger': logging.getLogger('shortlink-test'),
        'urlparse': urlparse,
        'get_settings': None,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), '<shortlink-functions>', 'exec'), namespace)
    return namespace


class ShortlinkProviderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ns = load_provider_functions()
        FakeSession.response = FakeResponse(200, '{"status":"success","shortenedUrl":"https://linkcut.org/xYz"}')

    async def test_linkcut_accepts_domain_and_https_domain(self):
        normalize = self.ns['normalize_shortener_domain']
        self.assertEqual(normalize('https://linkcut.org/'), 'linkcut.org')
        self.assertEqual(normalize('linkcut.org'), 'linkcut.org')
        result = await self.ns['create_shortlink']('https://t.me/', 'secret-key', 'https://linkcut.org')
        self.assertEqual(result, 'https://linkcut.org/xYz')
        self.assertEqual(FakeSession.last_url, 'https://linkcut.org/api')
        self.assertEqual(FakeSession.last_params, {'api': 'secret-key', 'url': 'https://t.me/'})

    async def test_empty_response_returns_none(self):
        FakeSession.response = FakeResponse(200, '')
        self.assertIsNone(await self.ns['create_shortlink']('https://t.me/', 'k', 'linkcut.org'))

    async def test_invalid_json_returns_none(self):
        FakeSession.response = FakeResponse(200, '<html>bad gateway</html>', 'text/html')
        self.assertIsNone(await self.ns['create_shortlink']('https://t.me/', 'k', 'linkcut.org'))

    async def test_http_error_returns_none(self):
        FakeSession.response = FakeResponse(403, '{"status":"error"}')
        self.assertIsNone(await self.ns['create_shortlink']('https://t.me/', 'k', 'linkcut.org'))

    async def test_missing_or_invalid_shortened_url_returns_none(self):
        FakeSession.response = FakeResponse(200, '{"status":"success","shortenedUrl":"not-a-url"}')
        self.assertIsNone(await self.ns['create_shortlink']('https://t.me/', 'k', 'linkcut.org'))

    async def test_other_provider_uses_shortzy_fallback(self):
        result = await self.ns['create_shortlink']('https://t.me/', 'k', 'short.example')
        self.assertEqual(result, 'https://short.example/converted')

    async def test_other_provider_quick_link_fallback(self):
        result = await self.ns['create_shortlink']('https://t.me/', 'k', 'convert-fails.test')
        self.assertEqual(result, 'https://short.example/quick')

    async def test_actual_generation_routes_to_selected_original_slot(self):
        calls = []
        async def fake_settings(group_id):
            return {
                'api': 'api1', 'shortner': 'provider1.test',
                'api_two': 'api2', 'shortner_two': 'provider2.test',
                'api_three': 'api3', 'shortner_three': 'provider3.test',
            }
        async def fake_create(link, api, site):
            calls.append((api, site))
            return 'https://short.example/result'
        self.ns['get_settings'] = fake_settings
        self.ns['create_shortlink'] = fake_create
        fn = self.ns['get_shortlink']
        self.assertEqual(await fn('https://target.test/', -100, False, False), 'https://short.example/result')
        self.assertEqual(await fn('https://target.test/', -100, True, False), 'https://short.example/result')
        self.assertEqual(await fn('https://target.test/', -100, False, True), 'https://short.example/result')
        self.assertEqual(calls, [('api1', 'provider1.test'), ('api2', 'provider2.test'), ('api3', 'provider3.test')])

    async def test_settings_validation_uses_shared_generator_and_no_unconditional_json(self):
        settings_source = (Path(__file__).resolve().parents[1] / 'plugins' / 'advanced_settings.py').read_text()
        self.assertIn('test_url = await create_shortlink("https://t.me/", value, domain)', settings_source)
        self.assertNotIn('response.json()', settings_source)
        commands_source = (Path(__file__).resolve().parents[1] / 'plugins' / 'commands.py').read_text()
        self.assertIn('verify = await get_shortlink(target_link, grp_id, is_second_shortener, is_third_shortener)', commands_source)


if __name__ == '__main__':
    unittest.main()
