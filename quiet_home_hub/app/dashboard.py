"""Build the TV's dashboard (see docs/DASHBOARD.md) and run allowlisted actions."""
import logging
import urllib.parse

log = logging.getLogger('quiet-home')

CONDITIONS = {
    'clear-night': 'Clear', 'cloudy': 'Cloudy', 'exceptional': 'Unusual weather', 'fog': 'Fog',
    'hail': 'Hail', 'lightning': 'Thunder', 'lightning-rainy': 'Thunderstorms', 'partlycloudy': 'Partly cloudy',
    'pouring': 'Heavy rain', 'rainy': 'Rain', 'snowy': 'Snow', 'snowy-rainy': 'Sleet', 'sunny': 'Sunny',
    'windy': 'Windy', 'windy-variant': 'Windy',
}
UNAVAILABLE = ('unavailable', 'unknown', None)


def read_state(ha, entity_id, missing=UNAVAILABLE):
    if not entity_id:
        return None
    try:
        state = ha.state(entity_id)
    except Exception as error:  # Home Assistant restarting or the entity misnamed.
        log.warning('Could not read %s: %s', entity_id, error)
        return None
    return state if state and state.get('state') not in missing else None


def _number(value, fallback):
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def controls(options, ha):
    items, light = [], read_state(ha, options.get('light'))
    if light:
        on, brightness = light['state'] == 'on', light['attributes'].get('brightness')
        item = {'id': light['entity_id'], 'kind': 'toggle', 'label': options.get('light_label') or 'Lights', 'state': 'on' if on else 'off'}
        if on and isinstance(brightness, (int, float)):
            item['detail'] = '%d%%' % round(brightness / 255 * 100)
        items.append(item)
    for entity_id in options.get('scenes') or []:
        # A scene that has never been activated reports 'unknown'; it still works.
        scene = read_state(ha, entity_id, missing=('unavailable', None))
        if scene:
            items.append({'id': scene['entity_id'], 'kind': 'scene', 'label': scene['attributes'].get('friendly_name') or entity_id})
    climate = read_state(ha, options.get('climate'))
    if climate:
        a = climate['attributes']
        items.append({
            'id': climate['entity_id'], 'kind': 'climate', 'label': options.get('climate_label') or 'Heating',
            'current': _number(a.get('current_temperature'), None), 'target': _number(a.get('temperature'), 20),
            'min': _number(a.get('min_temp'), 7), 'max': _number(a.get('max_temp'), 30), 'step': _number(a.get('target_temp_step'), 0.5),
            'state': 'heating' if a.get('hvac_action') == 'heating' else 'idle'})
    return items


def build(options, ha, library, notes, key):
    suffix = '?' + urllib.parse.urlencode({'key': key}) if key else ''
    data = {'version': 1, 'theme': options.get('theme', 'auto'),
            'backgrounds': {'rotateMinutes': options.get('rotate_minutes', 15), 'day': [], 'night': []}, 'widgets': []}
    sun = read_state(ha, 'sun.sun')
    if sun:
        data['sun'] = {'sunrise': sun['attributes'].get('next_rising'), 'sunset': sun['attributes'].get('next_setting')}
    weather = read_state(ha, options.get('weather'))
    if weather and isinstance(weather['attributes'].get('temperature'), (int, float)):
        data['weather'] = {'temperature': weather['attributes']['temperature'], 'condition': CONDITIONS.get(weather['state'], weather['state'].replace('-', ' ').capitalize())}
    for photo in library.photos():
        entry = {'url': 'photos/' + photo['id'] + suffix, 'caption': photo['caption']} if photo['caption'] else 'photos/' + photo['id'] + suffix
        for period in (('day', 'night') if photo['period'] == 'any' else (photo['period'],)):
            data['backgrounds'][period].append(entry)
    items = controls(options, ha)
    if items:
        data['widgets'].append({'type': 'controls', 'title': options.get('room_title') or 'Home', 'items': items})
    notes = notes or {}
    rows = [{'value': str(n.get('value', ''))[:24], 'label': str(n.get('label', ''))[:40]}
            for n in notes.get('items', []) if n.get('value') or n.get('label')]
    if rows:
        data['widgets'].append({'type': 'stats', 'title': notes.get('title') or 'Family', 'items': rows[:3]})
    return data


def act(options, ha, request):
    """Run one action from the TV. Only configured entities and safe values are accepted."""
    entity_id, action, value = request.get('id'), request.get('action'), request.get('value')
    if action == 'toggle' and entity_id and entity_id == options.get('light'):
        # homeassistant.toggle works for lights and for lamps on smart switches.
        ha.call('homeassistant', 'toggle', {'entity_id': entity_id})
    elif action == 'activate' and entity_id and entity_id in (options.get('scenes') or []):
        ha.call('scene', 'turn_on', {'entity_id': entity_id})
    elif action == 'set_temperature' and entity_id and entity_id == options.get('climate'):
        state = read_state(ha, entity_id)
        if not state or not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        a = state['attributes']
        if not _number(a.get('min_temp'), 7) <= value <= _number(a.get('max_temp'), 30):
            return False
        ha.call('climate', 'set_temperature', {'entity_id': entity_id, 'temperature': value})
    else:
        return False
    return True
