#!/usr/local/bin/python3.5

# Adapted from https://github.com/sh0oki/chromecastslack/tree/master
## Useful references
# https://github.com/home-assistant-libs/pychromecast/blob/master/pychromecast/__init__.py
# https://github.com/home-assistant-libs/pychromecast/blob/master/pychromecast/controllers/media.py
# https://github.com/home-assistant-libs/pychromecast/blob/master/pychromecast/controllers/receiver.py

from time import sleep
from multiprocessing import Lock
import logging
import os

import pychromecast
from pychromecast.controllers.media import MediaStatusListener
import bot

HEALTH_CHECK_INTERVAL = 60


class MediaUpdatesListener(MediaStatusListener):
    def __init__(self, player, bot):
        self._song = None
        self._player = player
        self._bot = bot
        self._lock = Lock()

    def new_media_status(self, status):
        logging.info('[%s] Got new_media_status %s' % (self._player, status.player_state))
        logging.info(status)
        if not status.player_is_playing and not status.player_is_paused and not status.player_is_idle:
            logging.info('[%s] Became inactive (%s), releasing Soundbridge' % (self._player, status.player_state))
            self._bot.disconnectSoundbridge()
            return

        title = status.title
        artist = status.artist
        album = status.album_name
        duration = status.duration
        song = f'{title} - {artist} - {album} - {duration}'
        self._lock.acquire(True)
        try:
            if song != self._song:
                self._song = song
                logging.info('New song: %s' % (self._song, ))
                self._bot.updateSongInfo(title, artist, album, duration, self._player)
        finally:
            self._lock.release()

        match status.player_state:
            case pychromecast.controllers.media.MEDIA_PLAYER_STATE_PLAYING:
                self._bot.updateState(bot.CCState.PLAYING)
            case pychromecast.controllers.media.MEDIA_PLAYER_STATE_BUFFERING:
                self._bot.updateState(bot.CCState.BUFFERING)
            case pychromecast.controllers.media.MEDIA_PLAYER_STATE_PAUSED:
                self._bot.updateState(bot.CCState.PAUSED)
            case _: # IDLE and UNKNOWN
                self._bot.updateState(bot.CCState.STOPPED)
    
    def load_media_failed(self, queue_item_id: int, error_code: int) -> None:
        '''Called when load media failed.'''
        pass # Ignore events.

class ChromecastManager(object):
    def __init__(self, bot, cast_filter):
        self.active_list = {}
        self.bot = bot
        self.cast_filter = cast_filter
        self._lock = Lock()
        self._browser = None

    def listenForChromecasts(self):
        '''(Re-)Starts listening to Chromecasts on the net.

        Will terminate all existing connections first, if any.

        '''
        # Stop and delete all listeners, if any.
        self._lock.acquire(True)
        try:
            uuids = list(self.active_list.keys())
            for uuid in uuids:
                cast = self.active_list[uuid]
                try:
                    cast.disconnect()
                    del cast
                except Exception as e:
                    logging.error('Error while disconnecting Chromecast listener: %s', e)
                del self.active_list[uuid]
        finally:
            self._lock.release()
        if self._browser:
            # Must stop listening only after all discovered instances have been
            # disconnected to avoid a logspam bug in pychromecast:
            # https://github.com/home-assistant-libs/pychromecast/issues/866
            self._browser.stop_discovery()
        # Do not retry indefinitely as Chromecast might be powered off for a
        # long time.
        self._browser = pychromecast.get_chromecasts(
                tries=3,
                timeout=5,
                retry_wait=10,
                blocking=False,
                callback=self.discoveryCallback
        )

    def healthCheck(self, uuid):
        '''Returns False if any check failed, True otherwise.'''
        if uuid not in self.active_list:
            return True
        cast = self.active_list[uuid]
        alive = cast.socket_client.is_alive()
        logging.info(f'Health check on Chromecast {cast.name} with UUID {uuid}: alive=={alive}.')
        if not alive:
            logging.warning(f'Chromecast {cast.name} with UUID {uuid} failed health check.')
        return alive

    def discoveryCallback(self, chromecast):
        '''Registers with the passed Chromecast instance.

        Does nothing if Chromcast is already known and healthy. If known but
        unhealthy, attempts to disconnect first before re-registering.
        '''
        logging.info(f'Discovery of {chromecast.name}')
        if self.cast_filter and chromecast.name not in self.cast_filter:
            logging.info(f'Ignoring discovered Chromecast {chromecast.name} due to filter list {self.cast_filter}')
            return
            
        if chromecast.uuid in self.active_list:
            if self.healthCheck(chromecast.uuid):
                # Skip known and alive entry.
                return
            # Remove unhealthy entry.
            self._lock.acquire(True)
            try:
                cast = self.active_list[chromecast.uuid]
                cast.disconnect()
                del self.active_list[chromecast.uuid]
            finally:
                self._lock.release()
        self.register(chromecast)

    # def poll(self):
        # casts, browser = pychromecast.get_chromecasts(tries=1, timeout=5)
        # for chromecast in casts:
            # if chromecast.uuid in self.active_list or (self.cast_filter and chromecast.name not in self.cast_filter):
                # continue
            # self.register(chromecast)
        # # browser.stop_discovery() # This triggers an infinite failure loop upon connection loss, https://github.com/home-assistant-libs/pychromecast/issues/866

    def register(self, cast):
        '''Registers with Chromecast and adds it to active_list if successful.'''
        if cast is None:
            logging.error('Registration failed [%s]' % (cast, ))
            return
        cc_name = cast.name

        media_listener = MediaUpdatesListener(cc_name, self.bot)
        self._lock.acquire(True)
        try:
            cast.media_controller.register_status_listener(media_listener)
            cast.wait()
            self.active_list[cast.uuid] = cast
        finally:
            self._lock.release()
        logging.info('[%s] Registered' % (cc_name, ))


def main():
    soundbridge_address = os.environ['SOUNDBRIDGE_IP']
    if not soundbridge_address:
        logging.fatal('IP address or name of Soundbridge needs to be specified in SOUNDBRIDGE_IP environment variable')
    cast_filter = os.environ['CHROMECAST_FILTER'].split(',')
    if cast_filter:
        logging.info(f'Only connecting to Chromecasts named {cast_filter}')
    else:
        logging.info(f'Will report status of all Chromecasts, use comma-sep values for CHROMECAST_FILTER environment variable to limit')

    m = ChromecastManager(bot.Bot(soundbridge_address), cast_filter)
    m.listenForChromecasts()
    while True:
        for uuid in list(m.active_list.keys()):
            if not m.healthCheck(uuid):
                # Drop all current connections and reinitalize to ensure healthy state.
                m.listenForChromecasts()
        sleep(HEALTH_CHECK_INTERVAL)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()

