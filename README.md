## How to use ?

- Navigate to your ROM source directory

```bash
cd /path/to/your/rom/source
```

- Download the script using wget

```bash
wget https://raw.githubusercontent.com/Saikrishna1504/build-script/main/ci_bot.py
```

Or alternatively using curl:

```bash
curl -O https://raw.githubusercontent.com/Saikrishna1504/build-script/main/ci_bot.py
```

- Make it executable

```bash
chmod +x ci_bot.py
```

- Edit the script and update the variables

```bash
nano ci_bot.py
```

- Update the configuration variables (see Variables section below)

- Run the script

```bash
python3 ci_bot.py -h
```

- Done

### Variables 

---------------

```python
# Your device codename :
DEVICE = ""

# Your build variant : [user/userdebug/eng] 
VARIANT = ""

# ROM type : Leave empty for standard ROMs (LineageOS, AOSP, etc.)
#            For AxionAOSP use: "axion-pico" / "axion-core" / "axion-vanilla"
ROM_TYPE = ""

# Official build flag : Set to "1" for official builds, leave empty for unofficial
CONFIG_OFFICIAL_FLAG = ""

# Your telegram group/channel chatid eg - "-xxxxxxxx"
CONFIG_CHATID = ""

# Your HTTP API bot token (get it from botfather) 
CONFIG_BOT_TOKEN = ""

# Set the Secondary chat/channel ID (It will only send error logs to that)
CONFIG_ERROR_CHATID = ""

# Set your rclone remote for uploading with rclone
RCLONE_REMOTE = ""

# Set your rclone folder name for uploading with rclone
RCLONE_FOLDER = ""

# Turn off server after build (save resource) [False/True]
POWEROFF = False

# Upload OTA JSON to termbin.com [True/False]
UPLOAD_OTA_JSON = True

# Custom JSON path, leave empty for axion, it only works if UPLOAD_OTA_JSON is set to true
OTA_JSON_PATH = "vendor/ota/your_device_name.json"

# Pin success message in chat [True/False]
PIN_SUCCESS_MESSAGE = True
```

### Requirements

```bash
# Python packages (Debian/Ubuntu)
sudo apt install python3-requests python3-pil

# Python packages (Arch Linux)
sudo pacman -S python-requests python-pillow

# Optional: Install rclone for cloud uploads
sudo apt install rclone git

# Required only if UPLOAD_OTA_JSON = True
sudo apt install netcat-openbsd
```

### Credits

Initial reference and base taken from  
[Build-Script](https://github.com/hipexscape/Build-Script) by [hipexscape](https://github.com/hipexscape).
