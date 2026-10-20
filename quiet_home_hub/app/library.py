"""Photo library on Home Assistant's media share.

Photos live in day/, night/ and any/ folders under /media/quiet-home, so they can
also be added through the Samba share or Home Assistant's media browser. Uploads
are rotated upright, resized for a 1080p TV and saved without metadata.
"""
import io
import json
import os
from pathlib import Path
import re
import threading
import uuid

from PIL import Image, ImageOps

PERIODS = ('day', 'night', 'any')
KINDS = {'.jpg', '.jpeg', '.png', '.webp'}
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$')
MAX_SIZE = (2560, 1440)
THUMB_SIZE = (480, 480)


class Library:
    def __init__(self, root):
        self.root = Path(root)
        self.lock = threading.Lock()
        for period in PERIODS:
            (self.root / period).mkdir(parents=True, exist_ok=True)
            (self.root / '.thumbs' / period).mkdir(parents=True, exist_ok=True)
        self.captions_file = self.root / 'captions.json'

    def _captions(self):
        try:
            return json.loads(self.captions_file.read_text())
        except (OSError, ValueError):
            return {}

    def _save_captions(self, captions):
        temp = self.captions_file.with_suffix('.tmp')
        temp.write_text(json.dumps(captions, indent=1, sort_keys=True))
        os.replace(temp, self.captions_file)

    def path(self, photo_id):
        """Return the file for 'period/name', or None if the id is not a library photo."""
        parts = str(photo_id).split('/')
        if len(parts) != 2 or parts[0] not in PERIODS or not NAME.match(parts[1]):
            return None
        file = self.root / parts[0] / parts[1]
        return file if file.suffix.lower() in KINDS and file.is_file() else None

    def photos(self, periods=PERIODS):
        captions, found = self._captions(), []
        for period in periods:
            for file in (self.root / period).iterdir():
                if file.is_file() and file.suffix.lower() in KINDS and NAME.match(file.name):
                    photo_id = period + '/' + file.name
                    found.append({'id': photo_id, 'period': period, 'caption': captions.get(photo_id, ''), 'added': file.stat().st_mtime})
        return sorted(found, key=lambda p: p['added'], reverse=True)

    def add(self, data, period, caption=''):
        if period not in PERIODS:
            raise ValueError('unknown period')
        try:
            image = Image.open(io.BytesIO(data))
            image = ImageOps.exif_transpose(image).convert('RGB')
        except Exception as error:
            raise ValueError('not a supported image') from error
        image.thumbnail(MAX_SIZE, Image.LANCZOS)
        name = uuid.uuid4().hex[:16] + '.jpg'
        # Saving without exif= drops camera metadata, including GPS location.
        image.save(self.root / period / name, 'JPEG', quality=85, optimize=True, progressive=True)
        self._thumbnail(image, period, name)
        photo_id = period + '/' + name
        with self.lock:
            captions = self._captions()
            if caption:
                captions[photo_id] = caption[:120]
                self._save_captions(captions)
        return photo_id

    def _thumbnail(self, image, period, name):
        thumb = image.copy()
        thumb.thumbnail(THUMB_SIZE, Image.LANCZOS)
        thumb.convert('RGB').save(self.root / '.thumbs' / period / (Path(name).stem + '.jpg'), 'JPEG', quality=80)

    def thumb(self, photo_id):
        file = self.path(photo_id)
        if not file:
            return None
        thumb = self.root / '.thumbs' / file.parent.name / (file.stem + '.jpg')
        if not thumb.is_file():
            # Photos copied in through Samba get a thumbnail on first view.
            with Image.open(file) as image:
                self._thumbnail(ImageOps.exif_transpose(image), file.parent.name, file.name)
        return thumb

    def update(self, photo_id, caption=None, period=None):
        file = self.path(photo_id)
        if not file:
            raise ValueError('unknown photo')
        with self.lock:
            captions = self._captions()
            text = captions.pop(photo_id, '')
            if period and period != file.parent.name:
                if period not in PERIODS:
                    raise ValueError('unknown period')
                old_thumb = self.root / '.thumbs' / file.parent.name / (file.stem + '.jpg')
                os.replace(file, self.root / period / file.name)
                if old_thumb.is_file():
                    os.replace(old_thumb, self.root / '.thumbs' / period / old_thumb.name)
                photo_id = period + '/' + file.name
            text = text if caption is None else caption[:120]
            if text:
                captions[photo_id] = text
            self._save_captions(captions)
        return photo_id

    def delete(self, photo_id):
        file = self.path(photo_id)
        if not file:
            raise ValueError('unknown photo')
        with self.lock:
            thumb = self.root / '.thumbs' / file.parent.name / (file.stem + '.jpg')
            file.unlink()
            if thumb.is_file():
                thumb.unlink()
            captions = self._captions()
            if captions.pop(photo_id, None) is not None:
                self._save_captions(captions)
