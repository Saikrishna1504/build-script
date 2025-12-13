#!/bin/bash

# Build Configuration. Required variables to compile the ROM.
DEVICE=""
VARIANT=""
CONFIG_OFFICIAL_FLAG=""
ROM_TYPE=""  # Set to "axion-pico", "axion-core", "axion-vanilla" for AxionAOSP, leave empty for standard ROMs (LineageOS, etc.)

# Telegram Configuration
CONFIG_CHATID="-"
CONFIG_BOT_TOKEN=""
CONFIG_ERROR_CHATID=""

# Rclone upload
RCLONE_REMOTE=""
RCLONE_FOLDER=""

# Turning off server after build or no
POWEROFF=""

# Script Constants. Required variables throughout the script.
RED=$(tput setaf 1)
YELLOW=$(tput setaf 3)
BOLD=$(tput bold)
RESET=$(tput sgr0)
BOLD_GREEN=${BOLD}$(tput setaf 2)
ROOT_DIRECTORY="$(pwd)"

# Post Constants. Required variables for posting purposes.
ROM_NAME="$(sed "s#.*/##" <<<"$(pwd)")"
ANDROID_VERSION=$(grep -oP '(?<=android-)[0-9]+' .repo/manifests/default.xml | head -n1)
OUT="$(pwd)/out/target/product/$DEVICE"
STICKER_URL="https://index.sauraj.eu.org/api/raw/?path=/sticker.webp"

# Parse ROM type and GMS variant for AxionAOSP
if [[ "$ROM_TYPE" == axion-* ]]; then
    # Extract GMS type from ROM_TYPE (e.g., axion-pico -> pico)
    AXION_GMS_TYPE="${ROM_TYPE#axion-}"
    ROM_TYPE_BASE="axion"
    
    # Set GMS variant based on type
    case "$AXION_GMS_TYPE" in
        pico)
            AXION_VARIANT="gms pico"
            ;;
        core)
            AXION_VARIANT="gms core"
            ;;
        vanilla)
            AXION_VARIANT="vanilla"
            ;;
        *)
            echo -e "${RED}Invalid AxionAOSP type: $AXION_GMS_TYPE. Use axion-pico, axion-core, or axion-vanilla${RESET}"
            exit 1
            ;;
    esac
else
    ROM_TYPE_BASE="${ROM_TYPE:-standard}"
fi

# CLI parameters. Fetch whatever input the user has provided.
while [[ $# -gt 0 ]]; do
    case $1 in
    -s | --sync)
        SYNC="1"
        ;;
    -c | --clean)
        CLEAN="1"
        ;;
    --c-d | --clean-device)
        CLEAN_DEVICE="1"
        ;;
    --d-o | --disk-optimization)
        DISK_OPTIMIZATION="1"
        ;;
    -h | --help)
        echo -e "\nNote: • You should specify all the mandatory variables in the script!
      • Just run "./$0" for normal build
Usage: ./build_rom.sh [OPTION]
Example:
    ./$(basename $0) -s -c or ./$(basename $0) --sync --clean

Mandatory options:
    No option is mandatory!, just simply run the script without passing any parameter.

Options:
    -s, --sync                 Sync sources before building.
    -c, --clean                Clean build directory before compilation.
    --c-d, --clean-device      Clean device build directory before compilation.
    --d-o, --disk-optimization Optimize disk before compilation. Build will not fail even if disk optimization script fails.\n"
        exit 1
        ;;
    *)
        echo -e "$RED\nUnknown parameter(s) passed: $1$RESET\n"
        exit 1
        ;;
    esac
    shift
done

# Configuration Checking. Exit the script if required variables aren"t set.
if [[ $DEVICE == "" ]] || [[ $VARIANT == "" ]]; then
    echo -e "$RED\nERROR: Please specify all of the mandatory variables!! Exiting now...$RESET\n"
    exit 1
fi

# Telegram Environment. Declare all of the related constants and functions.
export BOT_MESSAGE_URL="https://api.telegram.org/bot$CONFIG_BOT_TOKEN/sendMessage"
export BOT_EDIT_MESSAGE_URL="https://api.telegram.org/bot$CONFIG_BOT_TOKEN/editMessageText"
export BOT_FILE_URL="https://api.telegram.org/bot$CONFIG_BOT_TOKEN/sendDocument"
export BOT_STICKER_URL="https://api.telegram.org/bot$CONFIG_BOT_TOKEN/sendSticker"
export BOT_PIN_URL="https://api.telegram.org/bot$CONFIG_BOT_TOKEN/pinChatMessage"

send_message() {
    local RESPONSE=$(curl "$BOT_MESSAGE_URL" -d chat_id="$2" \
        -d "parse_mode=html" \
        -d "disable_web_page_preview=true" \
        -d text="$1")
    local MESSAGE_ID=$(echo "$RESPONSE" | grep -o '"message_id":[0-9]*' | cut -d':' -f2)
    echo "$MESSAGE_ID"
}

edit_message() {
    curl "$BOT_EDIT_MESSAGE_URL" -d chat_id="$2" \
        -d "parse_mode=html" \
        -d "disable_web_page_preview=true" \
        -d "message_id=$3" \
        -d text="$1"
}

send_file() {
    curl --progress-bar -F document=@"$1" "$BOT_FILE_URL" \
        -F chat_id="$2" \
        -F "disable_web_page_preview=true" \
        -F "parse_mode=html"
}

send_sticker() {
    curl -sL "$1" -o "$ROOT_DIRECTORY/sticker.webp"

    local STICKER_FILE="$ROOT_DIRECTORY/sticker.webp"

    curl "$BOT_STICKER_URL" -F sticker=@"$STICKER_FILE" \
        -F chat_id="$2" \
        -F "is_animated=false" \
        -F "is_video=false"
}

pin_message() {
    curl "$BOT_PIN_URL" \
        -d chat_id="$1" \
        -d message_id="$2"
}

upload_gofile() {
    SERVER=$(curl -X GET 'https://api.gofile.io/servers' | grep -Po '(store*)[^"]*' | tail -n 1)
    RESPONSE=$(curl -X POST https://${SERVER}.gofile.io/contents/uploadfile -F "file=@$1")
    HASH=$(echo "$RESPONSE" | grep -Po '(https://gofile.io/d/)[^"]*')

    echo "$HASH"
}

upload_rclone() {
    ZIPFILE=$1
    ZIPNAME=$(basename "$1")
    
    # Check if file already exists and auto-rename if needed
    REMOTE_FILE_LIST=$(rclone lsjson "$RCLONE_REMOTE:$RCLONE_FOLDER" 2>/dev/null | grep -o '"Name":"[^"]*"' | cut -d'"' -f4 || true)
    
    if echo "$REMOTE_FILE_LIST" | grep -q "^$ZIPNAME$"; then
        # File exists, create new name with (1), (2), etc.
        BASE="${ZIPNAME%.*}"
        EXT="${ZIPNAME##*.}"
        COUNT=1
        NEW_NAME="${BASE} (${COUNT}).${EXT}"
        
        while echo "$REMOTE_FILE_LIST" | grep -q "^$NEW_NAME$"; do
            COUNT=$((COUNT + 1))
            NEW_NAME="${BASE} (${COUNT}).${EXT}"
        done
        
        echo -e "$YELLOW\n⚠️  File exists. Auto-renaming to: $NEW_NAME$RESET"
        
        # Create temporary copy with new name
        TMP="/tmp/$NEW_NAME"
        cp "$ZIPFILE" "$TMP"
        ZIPFILE="$TMP"
        ZIPNAME="$NEW_NAME"
    fi
    
    # Upload the file
    rclone copy "$ZIPFILE" "$RCLONE_REMOTE:$RCLONE_FOLDER" \
        --progress \
        --transfers 1 \
        --checkers 8 \
        --retries 5 \
        --low-level-retries 20 \
        --timeout 1m \
        --contimeout 1m
    
    # Get shareable link
    HASH=$(rclone link "$RCLONE_REMOTE:$RCLONE_FOLDER/$ZIPNAME" 2>/dev/null || true)
    
    # Clean up temporary file if created
    if [[ "$ZIPFILE" == /tmp/* ]]; then
        rm -f "$ZIPFILE"
    fi
    
    echo "$HASH"
}

# Smart upload function with fallback
upload_file() {
    local FILE=$1
    local UPLOAD_URL=""
    
    # Check if rclone is configured
    if [ -n "$RCLONE_REMOTE" ] && [ -n "$RCLONE_FOLDER" ]; then
        echo -e "$BOLD_GREEN\nUploading $(basename $FILE) via rclone...$RESET"
        UPLOAD_URL=$(upload_rclone "$FILE")
        
        # Check if rclone upload was successful
        if [ -n "$UPLOAD_URL" ]; then
            echo "$UPLOAD_URL"
            return 0
        else
            echo -e "$YELLOW\nRclone upload failed, falling back to GoFile...$RESET"
        fi
    else
        echo -e "$YELLOW\nRclone not configured, using GoFile...$RESET"
    fi
    
    # Fallback to GoFile
    echo -e "$BOLD_GREEN\nUploading $(basename $FILE) via GoFile...$RESET"
    UPLOAD_URL=$(upload_gofile "$FILE")
    echo "$UPLOAD_URL"
}

send_message_to_error_chat() {
    local response=$(curl -s -X POST "$BOT_MESSAGE_URL" -d chat_id="$CONFIG_ERROR_CHATID" \
        -d "parse_mode=html" \
        -d "disable_web_page_preview=true" \
        -d text="$1")
    local message_id=$(echo "$response" | grep -o '"message_id":[0-9]*' | cut -d':' -f2)                 
    echo "$message_id"
}

send_file_to_error_chat() {
    curl --progress-bar -F document=@"$1" "$BOT_FILE_URL" \
        -F chat_id="$CONFIG_ERROR_CHATID" \
        -F "disable_web_page_preview=true" \
        -F "parse_mode=html"
}

fetch_progress() {
    local PROGRESS=$(
        sed -n '/ ninja/,$p' "$ROOT_DIRECTORY/build.log" |
            grep -Po '\d+% \d+/\d+' |
            tail -n1 |
            sed -e 's/ / (/; s/$/)/'
    )

    if [ -z "$PROGRESS" ]; then
        echo "Initializing the build system..."
    else
        echo "$PROGRESS"
    fi
}

# Cleanup Files. Nuke all of the files from previous runs.
if [ -f "out/error.log" ]; then
    rm -f "out/error.log"
fi

if [ -f "out/.lock" ]; then
    rm -f "out/.lock"
fi

if [ -f "$ROOT_DIRECTORY/build.log" ]; then
    rm -f "$ROOT_DIRECTORY/build.log"
fi

if [[ -n $DISK_OPTIMIZATION ]]; then
    # Include disk optimization script
    if [ -e "$HOME/io.sh" ]; then
        bash $HOME/io.sh
        echo -e "$BOLD_GREEN\nDisk optimization successful, continuing to proceed further...$RESET\n"
    else
        if ! bash <(curl -s https://raw.githubusercontent.com/KanishkTheDerp/scripts/master/io.sh); then
            echo -e "$BOLD_GREEN\nDisk optimization failed, continuing to proceed further...$RESET\n"
        else
            echo -e "$BOLD_GREEN\nDisk optimization successful, continuing to proceed further...$RESET\n"
        fi
    fi
fi

# Jobs Configuration. Determine the number of cores to be used.
CORE_COUNT=$(nproc --all)
CONFIG_SYNC_JOBS="$([ "$CORE_COUNT" -gt 8 ] && echo "12" || echo "$CORE_COUNT")"
CONFIG_COMPILE_JOBS="$CORE_COUNT"

# Execute Parameters. Do the work if specified.
if [[ -n $SYNC ]]; then
    # Send a notification that the syncing process has started.

    sync_start_message="🟡 | <i>Syncing sources!!</i>

<b>• ROM:</b> <code>$ROM_NAME</code>
<b>• DEVICE:</b> <code>$DEVICE</code>
<b>• ANDROID VERSION:</b> <code>$ANDROID_VERSION</code>
<b>• JOBS:</b> <code>$CONFIG_SYNC_JOBS Cores</code>
<b>• DIRECTORY:</b> <code>$(pwd)</code>"

    sync_message_id=$(send_message "$sync_start_message" "$CONFIG_CHATID")

    SYNC_START=$(TZ=Asia/Kolkata date +"%s")

    echo -e "$BOLD_GREEN\nStarting to sync sources now...$RESET\n"
    
    if ! repo sync -c -j$CONFIG_SYNC_JOBS --force-sync --no-clone-bundle --no-tags; then
        echo -e "$RED\nInitial sync has failed!!$RESET" && echo -e "$BOLD_GREEN\nTrying to sync again with lesser arguments...$RESET\n"

        if ! repo sync --force-sync; then
            echo -e "$RED\nSyncing has failed completely!$RESET" && echo -e "$BOLD_GREEN\nStarting the build now...$RESET\n"
        else
            SYNC_END=$(TZ=Asia/Kolkata date +"%s")
        fi
    else
        SYNC_END=$(TZ=Asia/Kolkata date +"%s")
    fi

    if [[ -n $SYNC_END ]]; then
        DIFFERENCE=$((SYNC_END - SYNC_START))
        MINUTES=$((($DIFFERENCE % 3600) / 60))
        SECONDS=$(($DIFFERENCE % 60))

        sync_finished_message="🟢 | <i>Sources synced!!</i>

<b>• ROM:</b> <code>$ROM_NAME</code>
<b>• DEVICE:</b> <code>$DEVICE</code>
<b>• ANDROID VERSION:</b> <code>$ANDROID_VERSION</code>
<b>• JOBS:</b> <code>$CONFIG_SYNC_JOBS Cores</code>
<b>• DIRECTORY:</b> <code>$(pwd)</code>

<i>Syncing took $MINUTES minutes(s) and $SECONDS seconds(s)</i>"

        edit_message "$sync_finished_message" "$CONFIG_CHATID" "$sync_message_id"
    else
        sync_failed_message="🔴 | <i>Syncing sources failed!!</i>
    
<i>Trying to compile the ROM now...</i>"

        edit_message "$sync_failed_message" "$CONFIG_CHATID" "$sync_message_id"
    fi
fi

if [[ -n $CLEAN ]]; then
    echo -e "$BOLD_GREEN\nNuking the out directory now...$RESET\n"
    rm -rf "out"
fi

if [[ -n $CLEAN_DEVICE ]]; then
    echo -e "$BOLD_GREEN\nNuking the device out directory now...$RESET\n"
    rm -rf "out/target/product/"$DEVICE""
fi

# Send a notification that the build process has started.

build_start_message="🟡 | <i>Compiling ROM...</i>

<b>• ROM:</b> <code>$ROM_NAME</code>
<b>• DEVICE:</b> <code>$DEVICE</code>
<b>• ANDROID VERSION:</b> <code>$ANDROID_VERSION</code>
<b>• JOBS:</b> <code>$CONFIG_COMPILE_JOBS Cores</code>
<b>• TYPE:</b> <code>$([ "$CONFIG_OFFICIAL_FLAG" == "1" ] && echo "Official" || echo "Unofficial")</code>
<b>• PROGRESS</b>: <code>Brunching...</code>"

build_message_id=$(send_message "$build_start_message" "$CONFIG_CHATID")

BUILD_START=$(TZ=Asia/Kolkata date +"%s")

# Start Compilation. Compile the ROM according to the configuration.
echo -e "$BOLD_GREEN\nSetting up the build environment...$RESET"

if [ "$ROM_TYPE_BASE" = "axion" ]; then
    # AxionAOSP build process
    echo -e "$BOLD_GREEN\nConfiguring device for AxionAOSP ($AXION_GMS_TYPE)...$RESET"
    source build/envsetup.sh
    
    if [ $? -eq 0 ]; then
        # Run axion device configuration
        # axion usage: axion <device_codename> [user|userdebug|eng] [gms [pico|core] | vanilla]
        # VARIANT contains build variant (user/userdebug/eng), AXION_VARIANT contains GMS type
        axion "$DEVICE" $VARIANT $AXION_VARIANT
        
        if [ $? -eq 0 ]; then
            echo -e "$BOLD_GREEN\nStarting AxionAOSP build now...$RESET"
            # ax usage: ax [-b|-fb|-br] [-j<num>] [user|eng|userdebug]
            ax -br -j$CONFIG_COMPILE_JOBS 2>&1 | tee -a "$ROOT_DIRECTORY/build.log" &
        else
            echo -e "$RED\nFailed to configure $DEVICE for AxionAOSP$RESET"
            
            build_failed_message="🔴 | <i>ROM compilation failed...</i>
    
<i>Failed at configuring $DEVICE for AxionAOSP...</i>"

            edit_message "$build_failed_message" "$CONFIG_CHATID" "$build_message_id"
            send_sticker "$STICKER_URL" "$CONFIG_CHATID"
            exit 1
        fi
    else
        echo -e "$RED\nFailed to setup build environment$RESET"
        
        build_failed_message="🔴 | <i>ROM compilation failed...</i>
    
<i>Failed at setting up build environment...</i>"

        edit_message "$build_failed_message" "$CONFIG_CHATID" "$build_message_id"
        send_sticker "$STICKER_URL" "$CONFIG_CHATID"
        exit 1
    fi
else
    # Standard ROM build process (LineageOS, etc.)
    source build/envsetup.sh

    if [ $? -eq 0 ]; then
        echo -e "$BOLD_GREEN\nStarting to build now...$RESET" 
        brunch "$DEVICE" "$VARIANT" 2>&1 | tee -a "$ROOT_DIRECTORY/build.log" &
    else
        echo -e "$RED\nFailed to brunch "$DEVICE"$RESET"

        build_failed_message="🔴 | <i>ROM compilation failed...</i>
    
<i>Failed at brunching $DEVICE...</i>"

        edit_message "$build_failed_message" "$CONFIG_CHATID" "$build_message_id"
        send_sticker "$STICKER_URL" "$CONFIG_CHATID"
        exit 1
    fi
fi

# Contiounsly update the progress of the build.
until [ -z "$(jobs -r)" ]; do
    if [ "$(fetch_progress)" = "$previous_progress" ]; then
        continue
    fi

    build_progress_message="🟡 | <i>Compiling ROM...</i>

<b>• ROM:</b> <code>$ROM_NAME</code>
<b>• DEVICE:</b> <code>$DEVICE</code>
<b>• ANDROID VERSION:</b> <code>$ANDROID_VERSION</code>
<b>• JOBS:</b> <code>$CONFIG_COMPILE_JOBS Cores</code>
<b>• TYPE:</b> <code>$([ "$CONFIG_OFFICIAL_FLAG" == "1" ] && echo "Official" || echo "Unofficial")</code>
<b>• PROGRESS:</b> <code>$(fetch_progress)</code>"

    edit_message "$build_progress_message" "$CONFIG_CHATID" "$build_message_id"

    previous_progress=$(fetch_progress)

    sleep 5
done

build_progress_message="🟡 | <i>Compiling ROM...</i>

<b>• ROM:</b> <code>$ROM_NAME</code>
<b>• DEVICE:</b> <code>$DEVICE</code>
<b>• ANDROID VERSION:</b> <code>$ANDROID_VERSION</code>
<b>• JOBS:</b> <code>$CONFIG_COMPILE_JOBS Cores</code>
<b>• TYPE:</b> <code>$([ "$CONFIG_OFFICIAL_FLAG" == "1" ] && echo "Official" || echo "Unofficial")</code>
<b>• PROGRESS:</b> <code>$(fetch_progress)</code>"

edit_message "$build_progress_message" "$CONFIG_CHATID" "$build_message_id"

# Upload Build. Upload the output ROM files to the index.
BUILD_END=$(TZ=Asia/Kolkata date +"%s")
DIFFERENCE=$((BUILD_END - BUILD_START))
HOURS=$(($DIFFERENCE / 3600))
MINUTES=$((($DIFFERENCE % 3600) / 60))

if [ -s "out/error.log" ]; then
    # Send a notification that the build has failed.
    build_failed_message="🔴 | <i>ROM compilation failed...</i>
    
<i>Check out the log below!</i>"

    send_message_to_error_chat "$build_failed_message"
    send_file_to_error_chat "out/error.log"
#     send_sticker "$STICKER_URL" "$CONFIG_CHATID"
else
    zip_file=$(find "$OUT" -maxdepth 1 -type f -name *$DEVICE*.zip -size +500M -printf "%T@ %p\n" | sort -nr | head -n 1 | awk '{print $2}')

    echo -e "$BOLD_GREEN\nStarting to upload the rom files now...$RESET\n"

    zip_file_url=$(upload_file "$zip_file")
    zip_file_md5sum=$(md5sum $zip_file | awk '{print $1}')
    zip_file_size=$(ls -sh $zip_file | awk '{print $1}')

    # Only upload boot images if vendor_boot.img exists
    if [ -f "$OUT/vendor_boot.img" ]; then
        vendor_boot_url=$(upload_file "$OUT/vendor_boot.img")
        vendor_boot_line="<b>• VENDOR_BOOT:</b> $vendor_boot_url"
        
        # Upload boot.img if exists
        if [ -f "$OUT/boot.img" ]; then
            boot_url=$(upload_file "$OUT/boot.img")
            boot_line="<b>• BOOT:</b> $boot_url"
        else
            boot_line=""
        fi
        
        # Upload init_boot.img if exists
        if [ -f "$OUT/init_boot.img" ]; then
            init_boot_url=$(upload_file "$OUT/init_boot.img")
            init_boot_line="<b>• INIT_BOOT:</b> $init_boot_url"
        else
            init_boot_line=""
        fi
    else
        vendor_boot_line=""
        boot_line=""
        init_boot_line=""
    fi

    build_finished_message="🟢 | <i>ROM compiled!!</i>

<b>• ROM:</b> <code>$ROM_NAME</code>
<b>• DEVICE:</b> <code>$DEVICE</code>
<b>• ANDROID VERSION:</b> <code>$ANDROID_VERSION</code>
<b>• TYPE:</b> <code>$([ "$CONFIG_OFFICIAL_FLAG" == "1" ] && echo "Official" || echo "Unofficial")</code>
<b>• SIZE:</b> <code>$zip_file_size</code>
<b>• MD5SUM:</b> <code>$zip_file_md5sum</code>
<b>• ROM:</b> $zip_file_url
$vendor_boot_line
$boot_line
$init_boot_line

<i>Compilation took $HOURS hours(s) and $MINUTES minutes(s)</i>"

    edit_message "$build_finished_message" "$CONFIG_CHATID" "$build_message_id"
    pin_message "$CONFIG_CHATID" "$build_message_id"
#     send_sticker "$STICKER_URL" "$CONFIG_CHATID"
fi

if [[ $POWEROFF == true ]]; then
echo -e "$BOLD_GREEN\nAyo, powering off server...$RESET"
sudo poweroff
fi
