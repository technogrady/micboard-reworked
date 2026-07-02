# Server Installation
Micboard server can be installed on many different platforms.  For small and portable systems, Micboard can run on a Raspberry Pi hidden in the back of a rack.  Ubuntu Server is recommended for large permanent installations.

The macOS app provides a great way to try Micboard before purchasing additional hardware.

## Debian (Ubuntu & Raspberry Pi)
Micboard requires Python 3 and Node.js 18 or newer.  The versions packaged with Debian 12+, Ubuntu 22.04+, and Raspberry Pi OS (bookworm) work out of the box.
```
$ sudo apt-get update
$ sudo apt-get install git python3-venv nodejs npm
```

Download micboard
```
$ git clone https://github.com/technogrady/micboard-reworked/
```

Install frontend dependencies via npm and build the micboard frontend
```
$ cd micboard-reworked/
$ npm install --omit=dev
$ npm run build
```

Debian 12 and newer do not allow `pip` to install packages system-wide.  Create a virtual environment for micboard and install its Python dependencies there
```
$ python3 -m venv venv
$ ./venv/bin/pip install -r py/requirements.txt
```

Run micboard
```
$ ./venv/bin/python py/micboard.py
```

Edit `User`, `WorkingDirectory`, and `ExecStart` within `micboard.service` to match your installation and install it as a service.  `ExecStart` should point at the python binary inside the virtual environment created above.
```
$ sudo cp micboard.service /etc/systemd/system/
$ sudo systemctl start micboard.service
$ sudo systemctl enable micboard.service
```

Check the [configuration](configuration.md) docs for more information on configuring micboard.

## macOS - Desktop Application (UNCHANGED)
Download and run micboard from the project's [GitHub Release](https://github.com/karlcswanson/micboard/releases/) page.  Add RF devices to the 'Slot Configuration' and press 'Save'.

Check the [configuration](configuration.md) docs for more information on configuring micboard.


## macOS - From Source (UNCHANGED)
Install the Xcode command-line tools
```
$ xcode-select --install
```

Install the homebrew package manager
```
$ /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
```

Install python3 and node
```
$ brew install python3 node
```

Download Micboard
```
$ git clone https://github.com/karlcswanson/micboard.git
```

Install micboard software dependencies via npm and pip
```
$ cd micboard/
$ npm install --only=prod
$ pip3 install -r py/requirements.txt
```

build the micboard frontend and run micboard
```
$ npm run build
$ python3 py/micboard.py
```

Check the [configuration](configuration.md) docs for more information on configuring micboard.

Restart micboard
```
$ python3 py/micboard.py
```

## Docker (UNCHANGED)
Download micboard from github
```
$ git clone https://github.com/karlcswanson/micboard.git
```

Build and run docker image
```
$ cd micboard/
$ docker build -t micboard .
$ docker-compose up
```
