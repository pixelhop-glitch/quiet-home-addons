"""Quiet Home hub: the TV's dashboard API and the parent app.

Port 8098 serves the TV on the home network. Port 8099 serves the parent app,
which Home Assistant exposes in its sidebar through ingress (Home Assistant
handles sign-in). Run with --dev for local testing against a fake Home Assistant.
"""
import argparse
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import os
from pathlib import Path
import re
import threading
import urllib.parse

import dashboard
from homeassistant import FakeHomeAssistant, HomeAssistant
from library import PERIODS, Library

log = logging.getLogger('quiet-home')
HERE = Path(__file__).resolve().parent
INGRESS_PROXY = '172.30.32.2'
DEFAULTS = {'tv_key': '', 'theme': 'auto', 'rotate_minutes': 15, 'room_title': 'Living room', 'light': '', 'light_label': 'Lights',
            'scenes': [], 'climate': '', 'climate_label': 'Heating', 'weather': ''}
DEV_OPTIONS = {'light': 'light.living_room', 'scenes': ['scene.movie_night'], 'climate': 'climate.heating', 'weather': 'weather.home', 'rotate_minutes': 1}
# Chosen on the sidebar Setup tab; they override add-on options. The TV key stays in the add-on options.
SETTINGS = ('theme', 'rotate_minutes', 'room_title', 'light', 'light_label', 'scenes', 'climate', 'climate_label', 'weather')
PICKERS = {'light': ('light', 'switch'), 'scene': ('scene',), 'climate': ('climate',), 'weather': ('weather',)}
ENTITY = re.compile(r'^[a-z_]+\.[a-z0-9_]+$')
STATIC = {'/': ('index.html', 'text/html; charset=utf-8'), '/parent.js': ('parent.js', 'text/javascript'), '/parent.css': ('parent.css', 'text/css')}
IMAGES = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp'}


class Hub:
    def __init__(self, options, ha, library, data_dir):
        self.base, self.ha, self.library = options, ha, library
        self.notes_file = Path(data_dir) / 'notes.json'
        self.settings_file = Path(data_dir) / 'settings.json'
        self.lock = threading.Lock()
        try:
            self.settings = json.loads(self.settings_file.read_text())
        except (OSError, ValueError):
            self.settings = {}

    @property
    def options(self):
        merged = dict(self.base)
        merged.update({k: v for k, v in self.settings.items() if k in SETTINGS})
        return merged

    def entities(self):
        groups = {kind: [] for kind in PICKERS}
        for state in self.ha.states():
            entity_id = state.get('entity_id', '')
            for kind, domains in PICKERS.items():
                if entity_id.split('.')[0] in domains:
                    groups[kind].append({'id': entity_id, 'name': state.get('attributes', {}).get('friendly_name') or entity_id})
        for items in groups.values():
            items.sort(key=lambda e: e['name'].lower())
        return groups

    def save_settings(self, data):
        def entity(value, kind):
            value = str(value or '')
            if value and (not ENTITY.match(value) or value.split('.')[0] not in PICKERS[kind]):
                raise ValueError('%s is not a %s entity' % (value, kind))
            return value
        def label(value, fallback):
            return str(value or '').strip()[:30] or fallback
        scenes = [entity(s, 'scene') for s in data.get('scenes') or [] if s]
        theme = data.get('theme', 'auto')
        if theme not in ('auto', 'bento', 'gallery'):
            raise ValueError('unknown theme')
        try:
            rotate = int(data.get('rotate_minutes', 15))
        except (TypeError, ValueError):
            raise ValueError('rotate_minutes must be a number')
        clean = {'theme': theme, 'rotate_minutes': max(1, min(240, rotate)),
                 'room_title': label(data.get('room_title'), 'Living room'),
                 'light': entity(data.get('light'), 'light'), 'light_label': label(data.get('light_label'), 'Lights'),
                 'scenes': list(dict.fromkeys(scenes))[:2],
                 'climate': entity(data.get('climate'), 'climate'), 'climate_label': label(data.get('climate_label'), 'Heating'),
                 'weather': entity(data.get('weather'), 'weather')}
        with self.lock:
            temp = self.settings_file.with_suffix('.tmp')
            temp.write_text(json.dumps(clean, indent=1))
            os.replace(temp, self.settings_file)
            self.settings = clean
        return clean

    @property
    def key(self):
        return self.options.get('tv_key') or ''

    def notes(self):
        try:
            return json.loads(self.notes_file.read_text())
        except (OSError, ValueError):
            return {'title': 'Family', 'items': []}

    def save_notes(self, notes):
        items = [{'value': str(n.get('value', ''))[:24], 'label': str(n.get('label', ''))[:40]} for n in notes.get('items', [])][:3]
        clean = {'title': str(notes.get('title') or 'Family')[:30], 'items': items}
        with self.lock:
            temp = self.notes_file.with_suffix('.tmp')
            temp.write_text(json.dumps(clean, indent=1))
            os.replace(temp, self.notes_file)
        return clean

    def dashboard(self, key=None):
        return dashboard.build(self.options, self.ha, self.library, self.notes(), self.key if key is None else key)

    def status(self):
        checks = []
        for label, entity_id in [('Light', self.options.get('light')), ('Heating', self.options.get('climate')),
                                 ('Weather', self.options.get('weather')), ('Sunrise and sunset', 'sun.sun')] + \
                                [('Scene', s) for s in self.options.get('scenes') or []]:
            if entity_id:
                missing = ('unavailable', None) if label == 'Scene' else dashboard.UNAVAILABLE
                checks.append({'label': label, 'entity': entity_id, 'found': dashboard.read_state(self.ha, entity_id, missing) is not None})
        counts = {p: len(self.library.photos((p,))) for p in PERIODS}
        return {'entities': checks, 'photos': counts, 'keySet': bool(self.key), 'tvPort': 8098}


class Handler(BaseHTTPRequestHandler):
    hub = None
    server_version = 'QuietHomeHub'

    def log_message(self, fmt, *args):
        log.debug('%s %s', self.address_string(), fmt % args)

    def parts(self):
        url = urllib.parse.urlsplit(self.path)
        return url.path, urllib.parse.parse_qs(url.query)

    def send(self, status, body, kind, extra=None):
        self.send_response(status)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        for name, value in (extra or {}).items():
            self.send_header(name, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def json(self, data, status=200):
        self.send(status, json.dumps(data).encode(), 'application/json', self.cors())

    def error(self, status, text):
        self.json({'error': text}, status)

    def cors(self):
        return {}

    def body(self, limit):
        length = int(self.headers.get('Content-Length') or 0)
        if length > limit:
            raise ValueError('upload too large')
        return self.rfile.read(length)

    def body_json(self):
        data = json.loads(self.body(65536) or b'{}')
        if not isinstance(data, dict):
            raise ValueError('expected an object')
        return data

    def image(self, file):
        if not file:
            return self.error(404, 'not found')
        self.send(200, file.read_bytes(), IMAGES.get(file.suffix.lower(), 'application/octet-stream'), {'Cache-Control': 'max-age=86400'})


class TVHandler(Handler):
    """Read-only dashboard, photos and allowlisted actions for the TV."""

    def cors(self):
        # The TV app is a packaged web app, so its requests are cross-origin.
        return {'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': 'Content-Type, X-Quiet-Home-Key',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'}

    def allowed(self, query):
        key = self.hub.key
        given = self.headers.get('X-Quiet-Home-Key') or (query.get('key') or [''])[0]
        return not key or hmac.compare_digest(given.encode(), key.encode())

    def do_OPTIONS(self):
        self.send(204, b'', 'text/plain', self.cors())

    def do_GET(self):
        path, query = self.parts()
        if not self.allowed(query):
            return self.error(401, 'TV key required')
        if path == '/api/dashboard':
            return self.json(self.hub.dashboard())
        if path.startswith('/photos/'):
            return self.image(self.hub.library.path(path[len('/photos/'):]))
        self.error(404, 'not found')

    def do_POST(self):
        path, query = self.parts()
        if not self.allowed(query):
            return self.error(401, 'TV key required')
        if path != '/api/action':
            return self.error(404, 'not found')
        try:
            ok = dashboard.act(self.hub.options, self.hub.ha, self.body_json())
        except (ValueError, KeyError) as error:
            return self.error(400, str(error))
        except Exception as error:
            log.warning('Action failed: %s', error)
            return self.error(502, 'Home Assistant did not accept the action')
        if not ok:
            return self.error(400, 'unsupported action')
        self.json(self.hub.dashboard())


class ParentHandler(Handler):
    """The parent app: photos, family notes and status. Reached through ingress."""
    ingress_only = True

    def gate(self):
        if self.ingress_only and self.client_address[0] != INGRESS_PROXY:
            self.error(403, 'Open Quiet Home from the Home Assistant sidebar')
            return False
        return True

    def do_GET(self):
        if not self.gate():
            return
        path, query = self.parts()
        if path in STATIC:
            name, kind = STATIC[path]
            return self.send(200, (HERE / 'static' / name).read_bytes(), kind)
        if path == '/api/photos':
            return self.json(self.hub.library.photos())
        if path == '/api/notes':
            return self.json(self.hub.notes())
        if path == '/api/status':
            return self.json(self.hub.status())
        if path == '/api/entities':
            try:
                return self.json(self.hub.entities())
            except Exception as error:
                log.warning('Could not list entities: %s', error)
                return self.error(502, 'Could not reach Home Assistant')
        if path == '/api/settings':
            return self.json({k: self.hub.options.get(k) for k in SETTINGS})
        if path == '/api/dashboard':
            return self.json(self.hub.dashboard(key=''))
        if path.startswith('/thumbs/'):
            return self.image(self.hub.library.thumb(path[len('/thumbs/'):]))
        if path.startswith('/photos/'):
            return self.image(self.hub.library.path(path[len('/photos/'):]))
        self.error(404, 'not found')

    def do_PUT(self):
        if not self.gate():
            return
        path, query = self.parts()
        if path != '/api/photos':
            return self.error(404, 'not found')
        try:
            photo_id = self.hub.library.add(self.body(40 * 1024 * 1024), (query.get('period') or ['any'])[0], (query.get('caption') or [''])[0])
        except ValueError as error:
            return self.error(400, str(error))
        self.json({'id': photo_id}, 201)

    def do_POST(self):
        if not self.gate():
            return
        path, _ = self.parts()
        try:
            data = self.body_json()
            if path == '/api/photos/update':
                return self.json({'id': self.hub.library.update(data.get('id'), data.get('caption'), data.get('period'))})
            if path == '/api/photos/delete':
                self.hub.library.delete(data.get('id'))
                return self.json({'ok': True})
            if path == '/api/notes':
                return self.json(self.hub.save_notes(data))
            if path == '/api/settings':
                return self.json(self.hub.save_settings(data))
        except ValueError as error:
            return self.error(400, str(error))
        self.error(404, 'not found')


def serve(handler, port):
    server = ThreadingHTTPServer(('0.0.0.0', port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--dev', action='store_true', help='use a fake Home Assistant and local folders')
    p.add_argument('--tv-port', type=int, default=8098)
    p.add_argument('--parent-port', type=int, default=8099)
    p.add_argument('--tv-key', default='', help='dev only: require this TV key')
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    options = dict(DEFAULTS)
    if a.dev:
        root = HERE.parent / '.dev'
        data_dir, media = root / 'data', root / 'media'
        data_dir.mkdir(parents=True, exist_ok=True)
        options.update(DEV_OPTIONS)
        options['tv_key'] = a.tv_key
        ha = FakeHomeAssistant()
        ParentHandler.ingress_only = False
    else:
        data_dir, media = Path('/data'), Path('/media/quiet-home')
        try:
            options.update(json.loads((data_dir / 'options.json').read_text()))
        except (OSError, ValueError):
            log.warning('No add-on options found; using defaults')
        ha = HomeAssistant('http://supervisor/core', os.environ.get('SUPERVISOR_TOKEN', ''))
    Handler.hub = Hub(options, ha, Library(media), data_dir)
    serve(TVHandler, a.tv_port)
    log.info('TV API on port %d, parent app on port %d%s', a.tv_port, a.parent_port, ' (dev)' if a.dev else '')
    serve(ParentHandler, a.parent_port)
    threading.Event().wait()


if __name__ == '__main__':
    main()
