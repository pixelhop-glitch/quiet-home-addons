"""Home Assistant access for the hub.

Inside the add-on, Supervisor provides SUPERVISOR_TOKEN and proxies Home
Assistant's REST API at http://supervisor/core, so no long-lived token is stored.
"""
from datetime import datetime
import json
import urllib.error
import urllib.request


class HomeAssistant:
    def __init__(self, url, token):
        self.url = url.rstrip('/')
        self.token = token

    def _request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        request = urllib.request.Request(self.url + path, data=data, method=method, headers={
            'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=6) as response:
            return json.loads(response.read() or b'null')

    def state(self, entity_id):
        try:
            return self._request('GET', '/api/states/' + entity_id)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    def call(self, domain, service, data):
        self._request('POST', '/api/services/%s/%s' % (domain, service), data)


class FakeHomeAssistant:
    """In-memory stand-in for local development, shaped like real entity states."""

    def __init__(self):
        today = datetime.now().astimezone()
        self.states = {
            'sun.sun': {'state': 'above_horizon', 'attributes': {
                'next_rising': today.replace(hour=7, minute=32, second=0, microsecond=0).isoformat(),
                'next_setting': today.replace(hour=18, minute=4, second=0, microsecond=0).isoformat()}},
            'weather.home': {'state': 'partlycloudy', 'attributes': {'temperature': 14}},
            'light.living_room': {'state': 'on', 'attributes': {'brightness': 204, 'friendly_name': 'Living room'}},
            'scene.movie_night': {'state': '2026-10-20T20:00:00+00:00', 'attributes': {'friendly_name': 'Movie'}},
            'climate.heating': {'state': 'heat', 'attributes': {
                'current_temperature': 19.5, 'temperature': 20, 'min_temp': 16, 'max_temp': 23,
                'target_temp_step': 0.5, 'hvac_action': 'heating', 'friendly_name': 'Heating'}},
        }

    def state(self, entity_id):
        state = self.states.get(entity_id)
        return dict(state, entity_id=entity_id) if state else None

    def call(self, domain, service, data):
        entity = self.states[data['entity_id']]
        if (domain, service) == ('light', 'toggle'):
            entity['state'] = 'off' if entity['state'] == 'on' else 'on'
        elif (domain, service) == ('scene', 'turn_on'):
            self.states['light.living_room'].update(state='on')
            self.states['light.living_room']['attributes']['brightness'] = 38
        elif (domain, service) == ('climate', 'set_temperature'):
            attributes = entity['attributes']
            attributes['temperature'] = data['temperature']
            attributes['hvac_action'] = 'heating' if data['temperature'] > attributes['current_temperature'] else 'idle'
