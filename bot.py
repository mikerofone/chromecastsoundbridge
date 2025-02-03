from enum import Enum
from dataclasses import dataclass
import logging
import re
import socket
import threading
import time

# It's either offline or reachable on the LAN, so timeout can be short.
SOUNDBRIDGE_CONNECT_TIMEOUT_SEC = 5
# By how many seconds updates should be delayed to avoid flicker.
SOUNDBRIDGE_UPDATE_DELAY_SEC = 1
# Dimensions of the Soundbridge's screen.
SCREEN_WIDTH = 280
SCREEN_HEIGHT = 16
# Character width in pixels in the default font.
CHARACTER_WIDTH = 6
# Height in pixels of a line of text (characters + margin).
LINE_HEIGHT = 8
# Pixels from left end of screen for drawing playback status symbol.
ICON_X_LEFT = SCREEN_WIDTH - 18
# Status border is drawn from right end of the screen.
STATUS_BORDER_WIDTH = 35

# An artist name matching this pattern indicates a song that's played from YTM
# instead of from a regular YouTube video.
YTM_SONG_ARTIST_RE_PATTERN = r'\[YT\] (.*) - Topic'

class CCState(Enum):
    IDLE = 0
    PLAYING = 1
    PAUSED = 2
    BUFFERING = 3
    STOPPED = 4
    INITIALIZING = 5

@dataclass
class PlaybackState:
    title : str | None = None
    artist : str | None = None
    album : str | None = None
    length_sec : int | None = None
    ccstate : CCState = CCState.INITIALIZING
    from_chromecast : str | None = None

class Bot(object):
    def __init__(self, soundbridge_address):
        self._soundbridge_address = soundbridge_address
        self._lock = threading.Lock()

        self._sock = None
        self._soundbridge_inited = False
        self._state = None
        # Timer for delayed screen updates to reduce flicker.
        self._delayed_output = None

        self._resetMetadata()

    def _resetMetadata(self):
        self._sock = None
        self._soundbridge_inited = False
        self._state = PlaybackState()
        # Abort stale updates, if any.
        with self._lock:
            if self._delayed_output:
                self._delayed_output.cancel()
            self._delayed_output = None

    def connectSoundbridge(self):
        if not self._sock:
            self._soundbridge_inited = False
            logging.info(f'Connecting to Soundbridge at {self._soundbridge_address}...')
            try:
                self._sock = socket.create_connection((self._soundbridge_address, 4444))
                self._sock.settimeout(SOUNDBRIDGE_CONNECT_TIMEOUT_SEC)
            except Exception as e:
                logging.info('Failed to connect within %s seconds: %s', SOUNDBRIDGE_CONNECT_TIMEOUT_SEC, e)
                if self._sock:
                    self.disconnectSoundbridge()
                return False
            logging.info('Connected with socket timeout of %s', self._sock.gettimeout())
        if not self._soundbridge_inited:
            self.initSoundbridge()
        return True

    def disconnectSoundbridge(self):
        if not self._sock:
            logging.info('Already disconnected')
            return

        try:
            self._sock.shutdown(socket.SHUT_RDWR)
            self._sock.close()
        except Exception as e:
            logging.error('Failed to close connection to Soundbridge: %s', e)
        finally:
            del self._sock
            self._sock = None
        self._resetMetadata()
        logging.info('Disconnected from Soundbridge.')

    def sendCommandsToSoundbridge(self, commands):
        if not self._sock:
            logging.info('Soundbridge not connected, not sending commands')
            return False
        if isinstance(commands, str):
            commands = [commands]
        try:
            for command in commands:
                self._sock.sendall(command + b'\n')
        except Exception as e:
            logging.error('Failed to send command to Soundbridge, disconnecting: %s', e)
            self.disconnectSoundbridge()
            return False
        return True

    def initSoundbridge(self):
        self._soundbridge_inited = self.sendCommandsToSoundbridge([
            b'sketch',
            b'encoding utf8',
            b'clear',
        ])

    def _drawStop(self):
        self.sendCommandsToSoundbridge([
            b'color 0',
            f'rect {ICON_X_LEFT - 1} 0 9 8'.encode(),
            b'color 1',
            f'rect {ICON_X_LEFT} 1 6 6'.encode(),
        ])

    def _drawPause(self):
        self.sendCommandsToSoundbridge([
            b'color 0',
            f'rect {ICON_X_LEFT - 1} 0 9 8'.encode(),
            b'color 1',
            f'rect {ICON_X_LEFT} 1 2 6'.encode(),
            f'rect {ICON_X_LEFT + 4} 1 2 6'.encode(),
        ])

    def _drawPlay(self):
        self.sendCommandsToSoundbridge([
            b'color 0',
            f'rect {ICON_X_LEFT - 1} 0 9 8'.encode(),
            b'color 1',
            f'rect {ICON_X_LEFT} 0 2 7'.encode(),
            f'rect {ICON_X_LEFT + 2} 1 2 5'.encode(),
            f'rect {ICON_X_LEFT + 4} 2 2 3'.encode(),
            f'point {ICON_X_LEFT + 6} 3'.encode(),
        ])

    def _drawBuffering(self):
        self.sendCommandsToSoundbridge([
            b'color 0',
            f'rect {ICON_X_LEFT - 1} 0 9 8'.encode(),
            b'color 1',
            f'line {ICON_X_LEFT} 0 {ICON_X_LEFT + 8} 0'.encode(),
            f'line {ICON_X_LEFT} 7 {ICON_X_LEFT + 8} 7'.encode(),
            f'line {ICON_X_LEFT} 1 {ICON_X_LEFT + 3} 4'.encode(),
            f'line {ICON_X_LEFT} 6 {ICON_X_LEFT + 3} 3'.encode(),
            f'line {ICON_X_LEFT + 7} 1 {ICON_X_LEFT + 4} 4'.encode(),
            f'line {ICON_X_LEFT + 7} 6 {ICON_X_LEFT + 4} 3'.encode(),
        ])

    def _truncate(self, text, max_num_chars):
        if len(text) > max_num_chars:
            text = text[:max_num_chars - 1] + '…'
        return text

    def _center(self, text, max_num_chars):
        left_indent_count = (max_num_chars - len(text)) // 2
        return (' ' * left_indent_count) + text

    def _printText(self, first_line, second_line, center = True):
        # First truncate, then escape as escaping doesn't affect rendered text length.
        max_text_width = SCREEN_WIDTH - STATUS_BORDER_WIDTH
        max_num_chars = max_text_width // CHARACTER_WIDTH
        first_line = self._truncate(first_line, max_num_chars)
        second_line = self._truncate(second_line, max_num_chars)
        if center:
            first_line = self._center(first_line, max_num_chars)
            second_line = self._center(second_line, max_num_chars)
        first_line = first_line.replace('\\', '\\\\').replace('"', '\\"')
        second_line = second_line.replace('\\', '\\\\').replace('"', '\\"')
        logging.info(f'DRAW ON SOUNDBRIDGE:\n  {first_line}\n  {second_line}')
        self.sendCommandsToSoundbridge([
            # Clear text area (= non-status area) first.
            b'color 0',
            f'rect 0 0 {SCREEN_WIDTH - STATUS_BORDER_WIDTH} {SCREEN_HEIGHT}'.encode(),
            b'color 1',
            f'text 0 0 "{first_line}"'.encode(),
            f'text 0 8 "{second_line}"'.encode(),
        ])

    def _printCurrentSong(self):
        # Omit album entirely if not set.
        album_info = f' | {self._state.album}' if self._state.album else ''
        self._printText(
            self._state.title or '<Unknown title>',
            f'{self._state.artist or "<Unknown artist>"}{album_info}'
        )

    def _printCurrentTime(self):
        if self._state.length_sec is not None:
            minutes = int(self._state.length_sec / 60)
            seconds = int(self._state.length_sec % 60)
            time_str = f'{minutes:d}:{seconds:02d}'
        else:
            minutes = 0
            seconds = 0
            time_str = '--:--'
        # Manually right-align.
        duration_x_start = SCREEN_WIDTH - (len(time_str) * CHARACTER_WIDTH)

        self.sendCommandsToSoundbridge([
            # Clear time area, i.e. second row of status border.
            b'color 0',
            f'rect {SCREEN_WIDTH - STATUS_BORDER_WIDTH} {LINE_HEIGHT} {STATUS_BORDER_WIDTH} {LINE_HEIGHT}'.encode(),
            b'color 1',
            f'text {duration_x_start} {LINE_HEIGHT} "{time_str}"'.encode(),
        ])

    def _redraw(self):
        try:
            with self._lock:
                logging.info(f'redrawing at {time.time()}')
                # Ensure connected and initialized, no-op if called repeatedly.
                if not self.connectSoundbridge():
                    logging.info('Soundbridge offline, not updating')
                    return
                self.sendCommandsToSoundbridge([
                    b'clear',
                ])

                if self._state.ccstate == CCState.INITIALIZING:
                    self._printText(f'{self._state.from_chromecast} is starting playback...', '', center=False)
                elif self._state.ccstate == CCState.STOPPED:
                    self._printText('End of playlist.', '', center=False)
                else:
                    self._printCurrentSong()

                self._printCurrentTime()
        finally:
            self._delayed_output = None

        match self._state.ccstate:
            case CCState.PLAYING:
                self._drawPlay()
            case CCState.PAUSED:
                self._drawPause()
            case CCState.BUFFERING | CCState.INITIALIZING:
                self._drawBuffering()
                # TODO: Add timer to display error if buffering > 5 sec. (e.g. force-stopped by youtube?)
            case CCState.STOPPED:
                self._drawStop()

    def _enqueueRedraw(self):
        with self._lock:
            if self._delayed_output:
                # Redraw already enqueued, nothing to do.
                return
            timer = threading.Timer(SOUNDBRIDGE_UPDATE_DELAY_SEC, self._redraw)
            timer.start()
            self._delayed_output = timer

    def updateState(self, state, cast_name):
        if state in [CCState.PLAYING, CCState.BUFFERING] and not (self._state.title or self._state.artist or self._state.album):
            state = CCState.INITIALIZING
        self._state.ccstate = state
        self._state.from_chromecast = cast_name
        self._enqueueRedraw()
        logging.info(f'enqueued redraw for state {self._state.ccstate} from {self._state.from_chromecast} at {time.time()}')

    def updateSongInfo(self, title, artist, album, length_sec, cast_name):
        #import traceback; traceback.print_stack()
        self._state.title = title
        # Hack: The YT metadata arrives earlier than the more detailed parsed one.
        # Attempt to detect that for a little cleaner output.
        if artist and (m := re.fullmatch(YTM_SONG_ARTIST_RE_PATTERN, artist)):
            # Song from YTM, extract artist name.
            self._state.artist = m[1]
        else:
            self._state.artist = artist
        self._state.album = album
        self._state.length_sec = length_sec
        self._state.from_chromecast = cast_name
        self._enqueueRedraw()
        logging.info(f'enqueued redraw for song {title} at {time.time()}')