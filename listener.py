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
import urllib.request
import json
import urllib
import collections

import pychromecast
from pychromecast.controllers.media import MediaStatusListener
import bot

HEALTH_CHECK_INTERVAL = 60

LastSong = collections.namedtuple('LastSong', 'title,artist,album,content_id')

class MediaUpdatesListener(MediaStatusListener):
    def __init__(self, player, bot):
        self._song = LastSong(None,None,None,None)
        self._player = player
        self._bot = bot
        self._lock = Lock()

    def new_media_status(self, status):
        logging.info('[%s] Got new_media_status %s' % (self._player, status.player_state))
        if not status.player_is_playing and not status.player_is_paused and not status.player_is_idle:
            logging.info('[%s] Became inactive (%s), releasing Soundbridge' % (self._player, status.player_state))
            self._bot.disconnectSoundbridge()
            return

        title = status.title
        artist = status.artist
        album = status.album_name
        duration = status.duration

        # Metadata delivery is a bit of a mess.
        # 1. Videos from YouTube instead of YTM don't come with title, artist etc extracted.
        # 2. When switching from songs on YTM to songs from YouTube, updates still contain the
        #    old extracted title/artist/album even though the content_id changes correctly.
        #    pychromecast bug: https://github.com/home-assistant-libs/pychromecast/issues/1018
        metadata_stale = (title, artist, album) == (self._song.title, self._song.artist, self._song.album)
        metadata_missing = not title
        can_lookup_by_content_id = status.content_type and 'youtube' in status.content_type and status.content_id
        has_new_content_id = status.content_id != self._song.content_id
        skip_metadata_update = False
        if metadata_stale or metadata_missing:
            skip_metadata_update = True
            # Only do lookup if it the metadata is missing or known to be stale (we have a newer content_id).
            if can_lookup_by_content_id and (metadata_missing or has_new_content_id):
                title, artist, success = self._extractMetadataFromYouTubeVideo(status.content_id)
                # Prefer displaying an error over reverting back to stale information.
                skip_metadata_update = success or metadata_stale
                album = None
                with self._lock:
                    # Only update content_id, so we can detect when we finally get fresh metadata.
                    self._song = self._song._replace(content_id=status.content_id)
                    logging.info('New song, only updated content-id: %s', self._song)
                self._bot.updateSongInfo(title, artist, album, duration, self._player)
        if not metadata_missing and not skip_metadata_update:
            with self._lock:
                self._song = LastSong(title=title, artist=artist, album=album, content_id=status.content_id)
                logging.info('New Song from metadata: %s', self._song)
            self._bot.updateSongInfo(title, artist, album, duration, self._player)

        match status.player_state:
            case pychromecast.controllers.media.MEDIA_PLAYER_STATE_PLAYING:
                self._bot.updateState(bot.CCState.PLAYING, self._player)
            case pychromecast.controllers.media.MEDIA_PLAYER_STATE_BUFFERING:
                self._bot.updateState(bot.CCState.BUFFERING, self._player)
            case pychromecast.controllers.media.MEDIA_PLAYER_STATE_PAUSED:
                self._bot.updateState(bot.CCState.PAUSED, self._player)
            case _: # IDLE and UNKNOWN
                self._bot.updateState(bot.CCState.STOPPED, self._player)

    def _extractMetadataFromYouTubeVideo(self, video_id):
        '''Retrieves the video metadata and returns (title, channel name, success).

        Adapted from https://stackoverflow.com/questions/1216029/get-title-from-youtube-videos.
        '''
        params = {'format': 'json', 'url': f'https://www.youtube.com/watch?v={video_id}'}
        url = 'https://www.youtube.com/oembed'
        query_string = urllib.parse.urlencode(params)
        url = url + '?' + query_string

        try:
            logging.info('Resolving metadata for YouTube video %s', video_id)
            with urllib.request.urlopen(url) as response:
                response_text = response.read()
                data = json.loads(response_text.decode())
                title = data['title']
        except urllib.error.HTTPError as http_e:
            if http_e.code == 403:
                return (f'<ID {video_id}>', '<From uploaded songs>', False)
            logging.error('Got HTTP %s for metadata of YT video %s: %s', http_e.code, video_id, http_e.reason)
            return (f'<YouTube ID {video_id}>', f'<HTTP {http_e.code}: {http_e.reason}>', False)
        except Exception as e:
            logging.error('Failed to retrieve metadata for YT video %s: %s', video_id, e)
            return (f'<YouTube ID {video_id}>', f'<{e}>', False)

        channel = f'[YT] {data["author_name"]}' if 'author_name' in data else '[YT] <unknown channel>'
        return (title, channel, True)

    def load_media_failed(self, queue_item_id: int, error_code: int) -> None:
        pass # Ignore failures.

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
    if 'CHROMECAST_FILTER' in os.environ:
        cast_filter = os.environ['CHROMECAST_FILTER'].split(',')
        logging.info(f'Only connecting to Chromecasts named {cast_filter}')
    else:
        cast_filter = None
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
    logging.basicConfig(level=logging.WARNING)
    pid_file_name = None
    if 'PID_FILE' in os.environ:
        pid_file_name = os.environ['PID_FILE']
        with open(pid_file_name, 'w', encoding='utf-8') as f:
            f.write(str(os.getpid()))
    try:
        main()
    finally:
        if pid_file_name:
            # Not handling exception since we're going don't anyways.
            os.remove(pid_file_name)

