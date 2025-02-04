# chromecastsoundbridge

Display your currently playing songs on that beautiful display of your ancient Roku / Pinnacle SoundBridge M1001!

This was adapted from <https://github.com/sh0oki/chromecastslack> which was an excellent starting point. Thank you, sh0oki!

The script will look for active Chromecasts in your LAN (you can specify filters), then display the currently playing song on the display of the specified Soundbridge via its network port and the `sketch` feature.

This script is intended to run permanently on a server (e.g. a NAS, [see below](#running-as-a-service-on-a-server)) and as such aims to gracefully handle the Chromecast and/or Soundbridge going offline for extended periods of time. I haven't tested it extensively in that mode yet, but tried to code it as defensively as I could. Use at your own risk.

## In a nutshell

1. Have a working Chromecast in your LAN, playing music from your favorite source (YouTube Music, Soundcloud, ...).
1. Install *chromecastsoundbridge* on any [computer](#installation) / [server](#running-as-a-service-on-a-server) in your LAN.
1. Specify your Chromecast's name and the IP address of the SoundBridge when launching `listener.py` ([see below](#usage))

### Installation

**NOTE:** This script requires Python >= 3.10. For older versions, you might need to replace my use of `select` in the code with `if ... elif ... else`.

```shell
git clone git@github.com:mikerofone/chromecastsoundbridge.git
cd chromecastsoundbridge
pip3 install -r ./requirements.txt
```

### Usage

```shell
CHROMECAST_FILTER="Living Room" SOUNDBRIDGE_IP=192.168.13.37 python3 ./listener.py
```

Use your favorite init script to execute the script after restart.

*CHROMECAST_FILTER* is optional, though I haven't tested what happens when more than one Chromecast is playing simultaneously.

## Demo

Here's my Pinnacle SoundBridge M1001 showing what's currently playing on a Chromecast Audio:

![A Pinnacle M1001 Soundbridge showing what's playing on a Chromecast in the network.](./examples/soundbridge_playing.jpg)

## Running as a service on a server

### Create a virtual Python environment

See instructions on <https://kb.synology.com/en-us/DSM/tutorial/Set_up_Python_virtual_environment_on_NAS>.

I named mine `/volume1/chromecastsoundbridge`.

**Caveats:**

1. *Don't blindly use `python3` for these and the following steps - ensure your version is >= 3.10 first!* My Synology's Python3 package was too old (3.8.6 as of writing). I had to first enable the [SynoCommunity repository](https://synocommunity.com/) (don't forget to close and reopen the Package Manager), get the Python 3.10 package from there, and use `python3.10` as the binary for all commands involved.

2. You might need to create the folder as root and then `chown` it to your preferred admin user.

### Install from GIT

**NOTE:** You're going to run my code on your NAS. Inspect what it does before you blindly trust me.

Download `scripts/reinstall_from_git.sh` to a temporary location your server and run it. If you didn't use the same parameters as I did above, you can specify two parameters:

1. The root of the virtual environment created above (defaults to mine if unset, `/volume1/chromecastsoundbridge`).
2. The basename of your Python3 binary (defaults to `python3.10` if unset).

For example:

```shell
wget https://github.com/mikerofone/chromecastsoundbridge/raw/master/scripts/reinstall_from_git.sh
chmod +x reinstall_from_git.sh
./reinstall_from_git.sh  # If you used my values.
./reinstall_from_git.sh /tmp/my_root_path python3  # If you didn't.
```

### Test it

There's now a `chromecastsoundbridge-master` directory in your environment root that contains the service. `scripts/run_service.sh` only requires the IP address of the SoundBridge, but also takes the Chromecast name filter, environment base directory and python3 basename as additional parameters if you need to set them.

```shell
cd chromecastsoundbridge-master
# Any of the following work:
scripts/run_service.sh 192.168.13.37
scripts/run_service.sh 192.168.13.37 "Living Room"
scripts/run_service.sh 192.168.13.37 "" /tmp/my_root_path python3
```

The script will run indefinitely until it's terminated externally (or crashes hard). In a second terminal, you can test whether `scripts/stop_service.sh` can bring the service down gracefully. The only optional pparameter it takes is, again, the environment root dir:

```shell
scripts/stop_service.sh
scripts/stop_service.sh /tmp/my_root_path
```

If the script shut down, you're all set!

### Start the service

After testing the scripts, you can create a task in the task scheduler for executing them. Simply copy their full path and any args as you tested them as the script to run. The script is designed to run indefinitely, so you don't need to schedule runs. You might want to enable termination notifications, just in case the script does crash.

**IMPORTANT:** Don't run it as root, as this creates unnecessary exploitation risk! Other than read access to the files, the user doesn't need any special permissions. You might want to create a guest-class user for running the service.

### Ensure it's always running

This is probably unnecessary, but in case you really want to ensure that the script is always running and automatically recovers from crashes (I do), you can create two scheduled tasks: One for stopping the current instance via `stop_service.sh`, and another one for starting it again via `run_service.sh` a minute later. **Make sure both scripts run as the same (non-privileged) user!**

There might be cleaner ways to implement this running as a service, but this is the best ~~hacky~~ ~~lazy~~ *pragmatic* way of doing it with the task scheduler.

I've set mine to run daily in the early morning hours, so I likely will never notice it.
