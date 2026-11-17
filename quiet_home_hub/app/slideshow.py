"""4K photo slideshow videos for the TV's video layer.

The TV draws apps at 1920×1080, but video reaches the 4K panel at full resolution
and gets the TV's picture processing. For each period the hub encodes one H.264
video in which every photo holds briefly and then crossfades into the next. The
launcher pauses on each hold and plays the crossfade when the photo is due to change.
After the last crossfade (back into the first photo) a final hold of the first photo
follows, so playback never reaches the end: the TV's player will not restart cleanly
from a finished stream. The launcher pauses there, then seeks back to the start.

Each segment (photo, then crossfade into the next photo) is cached by the pair of
files, so adding or removing a photo re-encodes only its neighbours. Segments are
joined without re-encoding. Every segment starts with a keyframe, so the TV can seek
straight to any photo.
"""
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time

WIDTH, HEIGHT, FPS = 3840, 2160, 25
HOLD_FRAMES, FADE_FRAMES = 50, 40  # 2 s on the photo, then a 1.6 s crossfade
FORMAT = 4  # bump when the encoding changes, so cached segments are rebuilt
NAME = re.compile(r'^(day|night)-[0-9a-f]{16}\.mp4$')
log = logging.getLogger('quiet-home')


class Slideshow:
    def __init__(self, library, root):
        self.library = library
        self.root = Path(root)
        self.segments = self.root / 'segments'
        self.segments.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = shutil.which('ffmpeg')
        self.wanted = threading.Event()
        if self.ffmpeg:
            threading.Thread(target=self._worker, name='slideshow', daemon=True).start()
            self.request()
        else:
            log.warning('ffmpeg not found: 4K photo videos are off; the TV shows normal photos')

    def request(self):
        """Ask for a rebuild check soon (after uploads, edits or deletions)."""
        self.wanted.set()

    def manifest(self, period):
        try:
            data = json.loads((self.root / (period + '.json')).read_text())
        except (OSError, ValueError):
            return None
        return data if (self.root / data.get('file', '')).is_file() else None

    def file(self, name):
        if not NAME.match(name):
            return None
        file = self.root / name
        return file if file.is_file() else None

    # ---- Building --------------------------------------------------------------
    def _worker(self):
        while True:
            # Also wake every 10 minutes to notice photos copied in through Samba.
            self.wanted.wait(600)
            time.sleep(5)  # let a burst of uploads settle
            self.wanted.clear()
            for period in ('day', 'night'):
                try:
                    self._build(period)
                except Exception as error:
                    log.warning('Could not build the %s photo video: %s', period, error)
            self._prune()

    def _photos(self, period):
        found = []
        for photo in self.library.photos():
            if photo['period'] in (period, 'any'):
                file = self.library.path(photo['id'])
                if file:
                    found.append((photo['id'], file))
        return found

    @staticmethod
    def _key(file):
        stat = file.stat()
        return '%s:%d:%d' % (file.name, stat.st_size, int(stat.st_mtime))

    def _segment_name(self, file, following):
        key = json.dumps([FORMAT, self._key(file), following and self._key(following)])
        return hashlib.sha256(key.encode()).hexdigest()[:24] + '.ts'

    def _build(self, period):
        photos = self._photos(period)
        manifest_file = self.root / (period + '.json')
        if not photos:
            manifest_file.unlink(missing_ok=True)
            return
        keys = [self._key(file) for _, file in photos]
        version = hashlib.sha256(json.dumps([FORMAT, WIDTH, HEIGHT, FPS, HOLD_FRAMES, FADE_FRAMES, keys]).encode()).hexdigest()[:16]
        current = self.manifest(period)
        if current and current.get('version') == version:
            return
        started = time.time()
        parts, segments, frames = [], [], 0
        for index, (photo_id, file) in enumerate(photos):
            following = photos[(index + 1) % len(photos)][1] if len(photos) > 1 else None
            length = HOLD_FRAMES + (FADE_FRAMES if following else 0)
            parts.append((self._segment(file, following), length))
            segments.append({'id': photo_id, 'start': round(frames * 1000 / FPS)})
            frames += length
        tail = None
        if len(photos) > 1:
            parts.append((self._segment(photos[0][1], None), HOLD_FRAMES))
            tail = round(frames * 1000 / FPS)
            frames += HOLD_FRAMES
        name = '%s-%s.mp4' % (period, version)
        listing = self.root / (period + '.txt')
        # MPEG-TS segments carry no exact length, so give the joiner each one's duration.
        listing.write_text(''.join("file '%s'\nduration %.3f\n" % (part, length / FPS) for part, length in parts))
        temp = self.root / (name + '.tmp')
        self._run(['-f', 'concat', '-safe', '0', '-i', str(listing), '-c', 'copy',
                   '-movflags', '+faststart', '-f', 'mp4', str(temp)])
        os.replace(temp, self.root / name)
        listing.unlink(missing_ok=True)
        manifest = {'version': version, 'file': name, 'segments': segments, 'tail': tail,
                    'hold': round(HOLD_FRAMES * 1000 / FPS), 'duration': round(frames * 1000 / FPS)}
        if current:
            # A TV may still be playing the old video; prune keeps it for an hour from now.
            os.utime(self.root / current['file'])
        temp = manifest_file.with_suffix('.tmp')
        temp.write_text(json.dumps(manifest))
        os.replace(temp, manifest_file)
        log.info('Built the %s photo video: %d photos in %.0f s', period, len(photos), time.time() - started)

    def _segment(self, file, following):
        out = self.segments / self._segment_name(file, following)
        if out.is_file():
            return out
        # Fill the screen like the launcher's background-size: cover.
        fit = 'scale=%d:%d:force_original_aspect_ratio=increase:flags=lanczos,crop=%d:%d,setsar=1' % (WIDTH, HEIGHT, WIDTH, HEIGHT)
        hold, fade = HOLD_FRAMES / FPS, FADE_FRAMES / FPS
        if following:
            inputs = ['-loop', '1', '-framerate', str(FPS), '-t', '%.3f' % (hold + fade), '-i', str(file),
                      '-loop', '1', '-framerate', str(FPS), '-t', '%.3f' % fade, '-i', str(following)]
            graph = '[0]%s[a];[1]%s[b];[a][b]xfade=transition=fade:duration=%.3f:offset=%.3f,format=yuv420p' % (fit, fit, fade, hold)
            frames = HOLD_FRAMES + FADE_FRAMES
        else:
            inputs = ['-loop', '1', '-framerate', str(FPS), '-t', '%.3f' % hold, '-i', str(file)]
            graph = '[0]%s,format=yuv420p' % fit
            frames = HOLD_FRAMES
        temp = out.with_suffix('.tmp')
        # One keyframe at the start of each segment lets the TV seek straight to a photo.
        self._run(inputs + ['-filter_complex', graph, '-frames:v', str(frames), '-r', str(FPS),
                            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '16', '-profile:v', 'high', '-level', '5.1',
                            '-pix_fmt', 'yuv420p', '-x264-params', 'keyint=%d:min-keyint=%d:scenecut=0' % (frames, frames),
                            '-threads', '2', '-an', '-f', 'mpegts', str(temp)])
        os.replace(temp, out)
        return out

    def _run(self, arguments):
        command = [self.ffmpeg, '-hide_banner', '-loglevel', 'error', '-y'] + arguments
        if shutil.which('nice'):
            command = ['nice', '-n', '19'] + command  # keep Home Assistant responsive
        result = subprocess.run(command, capture_output=True, timeout=900)
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors='replace').strip()[-300:] or 'ffmpeg failed')

    def _prune(self):
        """Delete segments no current video uses, and replaced videos after an hour."""
        keep_files, keep_parts = set(), set()
        for period in ('day', 'night'):
            manifest = self.manifest(period)
            if manifest:
                keep_files.add(manifest['file'])
            photos = self._photos(period)
            for index, (_, file) in enumerate(photos):
                following = photos[(index + 1) % len(photos)][1] if len(photos) > 1 else None
                keep_parts.add(self._segment_name(file, following))
            if photos:
                keep_parts.add(self._segment_name(photos[0][1], None))
        for file in self.root.glob('*-*.mp4'):
            if file.name not in keep_files and time.time() - file.stat().st_mtime > 3600:
                file.unlink(missing_ok=True)
        for file in self.segments.iterdir():
            if file.name not in keep_parts:
                file.unlink(missing_ok=True)
