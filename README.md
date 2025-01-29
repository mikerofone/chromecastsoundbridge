# chromecastsoundbridge

Display your currently playing songs on that beautiful display of your ancient Roku / Pinnacle SoundBridge M1001!

This was adapted from https://github.com/sh0oki/chromecastslack which was an excellent starting point. Thank you, sh0oki!

The script will look for active Chromecasts in your LAN, then report the currently played song to a Soundbridge via its network port and the `sketch` feature.

I tested this script with Python >= 3.10.12. Other versions should work, but haven't been tested.

## Setup
1. Have a working Chromecast in your LAN, playing music from your favorite source (Spotify, Soundcloud, ...).
1. TODO
1. Install *chromecastslack* on any computer in your LAN. 
1. TODO

## Installing
```
git clone git@github.com:mikerofone/chromecastsoundbridge.git
cd chromecastsoundbridge
pip3 install -r ./requirements.txt
```

## Usage
```
CHROMECAST_FILTER="Living Room" SOUNDBRIDGE_IP=192.168.13.37 python3 ./listener.py python3 listener.py
```
Use your favorite init script to execute the script after restart.
*CHROMECAST_FILTER* is optional, though I haven't tested what happens when more than one Chromecast is connected.

## Example

TODO
