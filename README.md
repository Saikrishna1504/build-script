# Script written in Bash for easy interaction between Ci and Us
Created by [hipexscape](https://github.com/hipexscape)

## How to use ?

- First fork this repo and fill the variables (defined below)
- Clone this repo using curl
- Then do

```
 bash ci_bot.sh -h
```

- Done

### Variables 

---------------
```bash
# Your device codename :
DEVICE=""

# Your build variant : [user/userdebug/eng] 
VARIANT=""

# Your telegram group/channel chatid eg - "-xxxxxxxx"
CONFIG_CHATID=""

# Your HTTP API bot token (get it from botfather) 
CONFIG_BOT_TOKEN=""

# Set the Seconday chat/channel ID (IT will only send error logs to that)
CONFIG_ERROR_CHATID=""

# Set your rclone remote for uploading with rclone
RCLONE_REMOTE=""

# Set your rclone folder name for uploading with rclone
RCLONE_FOLDER=""

# Turn off server after build (save resource) [false/true]
POWEROFF=""
```
