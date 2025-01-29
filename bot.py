import logging
import json
import os
import socket

SOUNDBRIDGE_CONNECT_TIMEOUT_SEC = 5

ICON_X_LEFT = 262

class Bot(object):
    def __init__(self, soundbridge_address):
        self._sock = None
        socket.setdefaulttimeout(SOUNDBRIDGE_CONNECT_TIMEOUT_SEC)
        self._soundbridge_address = soundbridge_address
        self._soundbridge_inited = False

    def connectSoundbridge(self):
        if not self._sock:
            self._soundbridge_inited = False
            logging.info(f'Connecting to Soundbridge at {self._soundbridge_address}...')
            try:
                self._sock = socket.create_connection((self._soundbridge_address, 4444))
            except Exception as e:
                logging.error('Failed to connect within %s seconds: %s', SOUNDBRIDGE_CONNECT_TIMEOUT_SEC, e)
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
            self._soundbridge_inited = False
        logging.info('Disconnected from Soundbridge.')

    def sendCommandsToSoundbridge(self, commands):
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

    def displayStop(self):
        self.sendCommandsToSoundbridge([
            b'color 0',
            f'rect {ICON_X_LEFT - 1} 0 9 8'.encode(),
            b'color 1',
            f'rect {ICON_X_LEFT} 1 6 6'.encode(),
        ])

    def displayPause(self):
        self.sendCommandsToSoundbridge([
            b'color 0',
            f'rect {ICON_X_LEFT - 1} 0 9 8'.encode(),
            b'color 1',
            f'rect {ICON_X_LEFT} 1 2 6'.encode(),
            f'rect {ICON_X_LEFT + 4} 1 2 6'.encode(),
        ])

    def displayPlay(self):
        self.sendCommandsToSoundbridge([
            b'color 0',
            f'rect {ICON_X_LEFT - 1} 0 9 8'.encode(),
            b'color 1',
            f'rect {ICON_X_LEFT} 0 2 7'.encode(),
            f'rect {ICON_X_LEFT + 2} 1 2 5'.encode(),
            f'rect {ICON_X_LEFT + 4} 2 2 3'.encode(),
            f'point {ICON_X_LEFT + 6} 3'.encode(),
        ])

    def displayBuffering(self):
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
        
    def displaySongInfo(self, title, artist, album, length_sec, cast_name):
        # Ensure connected and initialized, no-op if called repeatedly.
        self.connectSoundbridge()

        if not title and not artist and not album:
            # Playing but no metadata happens on first play after starting cast.
            first_line = f"{cast_name} is starting playback..."
            second_line = ""
        else:
            # Regular playback update
            title = title or "<Unknown title>"
            artist = artist or "<Unknown artist>"
            album = album or "<Unknown album>"
            first_line = title
            second_line = f'{artist} | {album}'
        first_line = first_line.replace("\\", "\\\\").replace("\"", "\\\"")
        second_line = second_line.replace("\\", "\\\\").replace("\"", "\\\"")
        minutes = int(length_sec / 60)
        seconds = int(length_sec % 60)
        # Manually right-align.
        duration_x_start = 251 if minutes > 9 else 257
        status_border_width = 35 if minutes > 9 else 32
        
        self.sendCommandsToSoundbridge([
            b'clear',
            f'text c 0 "{first_line}"'.encode(),
            f'text c 8 "{second_line}"'.encode(),
            b'color 0',
            f'rect {280 - status_border_width} 0 {status_border_width} 16'.encode(),
            b'color 1',
            f'text {duration_x_start} 8 "{minutes:d}:{seconds:02d}"'.encode(),
        ])
        logging.info(f'DRAW ON SOUNDBRIDGE FOR {cast_name}:\n  {first_line}\n  {second_line}')

