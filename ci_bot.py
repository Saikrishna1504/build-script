#!/usr/bin/env python3
"""
CI Bot - Automated Android ROM Build Script with Telegram Notifications
Complete Python implementation
"""

import os
import sys
import subprocess
import time
import re
import requests
import signal
import argparse
import hashlib
from pathlib import Path
from datetime import datetime
from threading import Thread

# ============================================================================
# CONFIGURATION - Edit these values before running
# ============================================================================

# Build Configuration
DEVICE = ""                     # Your device codename (e.g., "cancunf", "begonia")
VARIANT = ""                    # Build variant: "user", "userdebug", or "eng"
CONFIG_OFFICIAL_FLAG = ""       # Set to "1" for official builds, leave "" for unofficial
ROM_TYPE = ""                   # For AxionAOSP: "axion-pico", "axion-core", "axion-vanilla"
                                # For standard ROMs (LineageOS, AOSP): leave ""

# Telegram Configuration
CONFIG_CHATID = ""              # Your Telegram chat/group ID (e.g., "-100123")
CONFIG_BOT_TOKEN = ""           # Your bot token from @BotFather
CONFIG_ERROR_CHATID = ""        # Chat ID for error logs (can be same as CONFIG_CHATID)

# Rclone Configuration (Optional - will use GoFile as fallback)
RCLONE_REMOTE = ""              # Your rclone remote name (e.g., "gdrive", "drive")
RCLONE_FOLDER = ""              # Folder path in remote (leave "" if remote points to folder root)

# Power Management
POWEROFF = False                # Set to True to shutdown server after build completes

# ============================================================================
# GLOBALS
# ============================================================================

ROOT_DIRECTORY = os.getcwd()
ROM_NAME = os.path.basename(ROOT_DIRECTORY)
BUILD_LOG = os.path.join(ROOT_DIRECTORY, "build.log")
OUT_DIR = ""
ANDROID_VERSION = ""
GITHUB_ORG_AVATAR = ""
build_message_id = None
use_banner = False
build_process = None
previous_progress = ""

# ============================================================================
# TELEGRAM FUNCTIONS
# ============================================================================

def send_message(text, chat_id=None):
    """Send text message to Telegram"""
    if chat_id is None:
        chat_id = CONFIG_CHATID
    
    url = f"https://api.telegram.org/bot{CONFIG_BOT_TOKEN}/sendMessage"
    data = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    
    try:
        response = requests.post(url, data=data, timeout=30)
        result = response.json()
        if result.get('ok'):
            return result['result']['message_id']
    except Exception as e:
        print(f"Error sending message: {e}", file=sys.stderr)
    return None

def send_photo(photo_path, caption, chat_id=None):
    """Send photo with caption to Telegram"""
    if chat_id is None:
        chat_id = CONFIG_CHATID
    
    url = f"https://api.telegram.org/bot{CONFIG_BOT_TOKEN}/sendPhoto"
    
    try:
        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {
                'chat_id': chat_id,
                'caption': caption,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, files=files, data=data, timeout=30)
            result = response.json()
            
            if result.get('ok'):
                return result['result']['message_id']
            else:
                print(f"Error sending photo: {result.get('description')}", file=sys.stderr)
    except Exception as e:
        print(f"Error sending photo: {e}", file=sys.stderr)
    return None

def send_file(file_path, chat_id=None):
    """Send file to Telegram"""
    if chat_id is None:
        chat_id = CONFIG_CHATID
    
    url = f"https://api.telegram.org/bot{CONFIG_BOT_TOKEN}/sendDocument"
    
    try:
        with open(file_path, 'rb') as file:
            files = {'document': file}
            data = {
                'chat_id': chat_id,
                'parse_mode': 'HTML'
            }
            
            response = requests.post(url, files=files, data=data, timeout=300)
            result = response.json()
            
            if result.get('ok'):
                return result['result']['message_id']
    except Exception as e:
        print(f"Error sending file: {e}", file=sys.stderr)
    return None

def edit_message(message_id, text, chat_id=None, reply_markup=None):
    """Edit text message"""
    if chat_id is None:
        chat_id = CONFIG_CHATID
    
    url = f"https://api.telegram.org/bot{CONFIG_BOT_TOKEN}/editMessageText"
    data = {
        'chat_id': chat_id,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    
    if reply_markup:
        data['reply_markup'] = reply_markup
    
    try:
        response = requests.post(url, json=data, timeout=30)
        result = response.json()
        if not result.get('ok') and 'not modified' not in result.get('description', ''):
            print(f"Error editing message: {result.get('description')}", file=sys.stderr)
    except Exception as e:
        print(f"Error editing message: {e}", file=sys.stderr)

def edit_photo_caption(message_id, caption, chat_id=None, reply_markup=None):
    """Edit photo caption"""
    if chat_id is None:
        chat_id = CONFIG_CHATID
    
    url = f"https://api.telegram.org/bot{CONFIG_BOT_TOKEN}/editMessageCaption"
    data = {
        'chat_id': chat_id,
        'message_id': message_id,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    
    if reply_markup:
        data['reply_markup'] = reply_markup
    
    try:
        response = requests.post(url, json=data, timeout=30)
        result = response.json()
        if not result.get('ok') and 'not modified' not in result.get('description', ''):
            print(f"Error editing caption: {result.get('description')}", file=sys.stderr)
    except Exception as e:
        print(f"Error editing caption: {e}", file=sys.stderr)

def create_download_buttons(rom_url, boot_images=None):
    """Create inline keyboard with download buttons"""
    buttons = []
    
    # ROM download button (always first)
    buttons.append([{"text": "📥 Download ROM", "url": rom_url}])
    
    # Boot image buttons (if provided)
    if boot_images:
        boot_row = []
        for img_name, img_url in boot_images.items():
            # Create button text without emoji
            button_text = img_name.replace('.img', '').replace('_', ' ').title()
            boot_row.append({"text": button_text, "url": img_url})
            
            # Add row if we have 2 buttons (max 2 per row for readability)
            if len(boot_row) == 2:
                buttons.append(boot_row)
                boot_row = []
        
        # Add remaining buttons
        if boot_row:
            buttons.append(boot_row)
    
    return {"inline_keyboard": buttons}

# ============================================================================
# BANNER GENERATION
# ============================================================================

def fetch_github_logo():
    """Fetch ROM logo from GitHub org avatar"""
    if not GITHUB_ORG_AVATAR:
        print("⚠️  No GitHub org avatar URL configured")
        return None
    
    logo_file = os.path.join(ROOT_DIRECTORY, "rom_logo.png")
    
    try:
        print(f"📥 Downloading logo from: {GITHUB_ORG_AVATAR}")
        response = requests.get(GITHUB_ORG_AVATAR, timeout=10)
        if response.status_code == 200:
            with open(logo_file, 'wb') as f:
                f.write(response.content)
            print(f"✅ Logo saved to: {logo_file}")
            return logo_file
        else:
            print(f"❌ Failed to download logo: HTTP {response.status_code}")
    except Exception as e:
        print(f"❌ Error downloading logo: {e}")
    
    return None

def generate_build_banner():
    """Generate build banner image using ImageMagick (similar to reference image)"""
    output_file = os.path.join(ROOT_DIRECTORY, "build_banner.png")
    
    try:
        # Check if ImageMagick is available
        subprocess.run(['convert', '--version'], capture_output=True, check=True)
        
        # Create gradient background (blue to purple like reference)
        subprocess.run([
            'convert', '-size', '1920x1080',
            'gradient:#2E3B8E-#6B2E8E',
            output_file
        ], check=True, capture_output=True)
        
        # Fetch ROM logo
        logo_file = fetch_github_logo()
        
        if logo_file and os.path.exists(logo_file):
            # Create a perfect circular logo with shadow/glow effect
            circle_file = os.path.join(ROOT_DIRECTORY, "logo_circle.png")
            mask_file = os.path.join(ROOT_DIRECTORY, "mask.png")
            shadow_file = os.path.join(ROOT_DIRECTORY, "logo_shadow.png")
            
            # Step 1: Resize logo to square
            subprocess.run([
                'convert', logo_file,
                '-resize', '400x400',
                '-gravity', 'center',
                '-extent', '400x400',
                '-background', 'white',
                '-alpha', 'remove',
                circle_file
            ], check=True, capture_output=True)
            
            # Step 2: Create circular mask
            subprocess.run([
                'convert',
                '-size', '400x400',
                'xc:black',
                '-fill', 'white',
                '-draw', 'circle 200,200 200,0',
                mask_file
            ], check=True, capture_output=True)
            
            # Step 3: Apply mask to create perfect circle
            subprocess.run([
                'convert', circle_file, mask_file,
                '-alpha', 'off',
                '-compose', 'copy_opacity',
                '-composite',
                circle_file
            ], check=True, capture_output=True)
            
            # Step 4: Create shadow/glow effect
            subprocess.run([
                'convert', circle_file,
                '(', '+clone',
                '-background', 'black',
                '-shadow', '80x8+0+0', ')',
                '+swap',
                '-background', 'none',
                '-layers', 'merge',
                '+repage',
                shadow_file
            ], check=True, capture_output=True)
            
            # Step 5: Composite logo with shadow onto banner
            subprocess.run([
                'convert', output_file, shadow_file,
                '-gravity', 'west',
                '-geometry', '+150+0',
                '-composite',
                output_file
            ], check=True, capture_output=True)
            
            # Cleanup
            for temp_file in [mask_file, shadow_file]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            
            # Add ROM name (large, bold, centered on right side)
            subprocess.run([
                'convert', output_file,
                '-gravity', 'center',
                '-pointsize', '200',
                '-fill', 'white',
                '-font', 'DejaVu-Sans-Bold',
                '-annotate', '+350-100', ROM_NAME.upper(),
                output_file
            ], check=True, capture_output=True)
            
            # Add device info (below ROM name)
            info_text = f"Device: {DEVICE}  |  Android {ANDROID_VERSION}"
            subprocess.run([
                'convert', output_file,
                '-gravity', 'center',
                '-pointsize', '65',
                '-fill', 'white',
                '-font', 'DejaVu-Sans',
                '-annotate', '+350+80', info_text,
                output_file
            ], check=True, capture_output=True)
            
            # Cleanup temp files
            for temp_file in [circle_file, logo_file]:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
        else:
            # No logo found, create text-only banner
            subprocess.run([
                'convert', output_file,
                '-gravity', 'center',
                '-pointsize', '180',
                '-fill', 'white',
                '-font', 'DejaVu-Sans-Bold',
                '-annotate', '+0-100', ROM_NAME.upper(),
                '-pointsize', '80',
                '-fill', '#E0E7FF',
                '-annotate', '+0+50', f'Device: {DEVICE}  |  Android {ANDROID_VERSION}',
                output_file
            ], check=True, capture_output=True)
        
        return output_file if os.path.exists(output_file) else None
        
    except Exception as e:
        print(f"Error generating banner: {e}", file=sys.stderr)
        return None

# ============================================================================
# BUILD FUNCTIONS
# ============================================================================

def fetch_progress():
    """Fetch build progress from build.log"""
    if not os.path.exists(BUILD_LOG):
        return "Initializing..."
    
    try:
        with open(BUILD_LOG, 'r') as f:
            lines = f.readlines()
        
        # Find ninja progress lines
        for line in reversed(lines):
            match = re.search(r'(\d+)% (\d+/\d+)', line)
            if match:
                return f"{match.group(1)}% ({match.group(2)})"
        
        return "Initializing the build system..."
    except:
        return "Initializing..."

def tail_build_log():
    """Tail build log and print to console"""
    last_position = 0
    
    while build_process and build_process.poll() is None:
        if os.path.exists(BUILD_LOG):
            try:
                with open(BUILD_LOG, 'r') as f:
                    f.seek(last_position)
                    new_lines = f.readlines()
                    last_position = f.tell()
                    
                    for line in new_lines:
                        # Print build output to console
                        print(line.rstrip())
            except:
                pass
        
        time.sleep(0.5)

def monitor_progress():
    """Monitor build progress and update Telegram"""
    global previous_progress, build_message_id, use_banner
    
    while build_process and build_process.poll() is None:
        current_progress = fetch_progress()
        
        if current_progress != previous_progress:
            # Print progress to console (stderr to not mix with build output)
            print(f"\n🔨 Build Progress: {current_progress}\n", file=sys.stderr)
            
            if use_banner:
                caption = f"""<b>🔨 Building {ROM_NAME}</b>

<b>Device:</b> {DEVICE} | <b>Android:</b> {ANDROID_VERSION}
<b>Type:</b> {'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'}

<b>⏳ Progress:</b> {current_progress}"""
                edit_photo_caption(build_message_id, caption)
            else:
                text = f"""🟡 | <i>Compiling ROM...</i>

<b>• ROM:</b> <code>{ROM_NAME}</code>
<b>• DEVICE:</b> <code>{DEVICE}</code>
<b>• ANDROID VERSION:</b> <code>{ANDROID_VERSION}</code>
<b>• TYPE:</b> <code>{'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'}</code>
<b>• PROGRESS:</b> <code>{current_progress}</code>"""
                edit_message(build_message_id, text)
            
            previous_progress = current_progress
        
        time.sleep(5)

def upload_gofile(file_path):
    """Upload file to GoFile with progress"""
    file_name = os.path.basename(file_path)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    
    print(f"📤 Uploading via GoFile: {file_name} ({file_size_mb:.2f} MB)")
    
    try:
        # Get server
        print("Getting server...")
        response = requests.get('https://api.gofile.io/servers', timeout=30)
        server = response.json()['data']['servers'][0]['name']
        print(f"Server: {server}")
        
        # Upload file
        print("Uploading to GoFile (this may take a while)...")
        with open(file_path, 'rb') as f:
            files = {'file': f}
            response = requests.post(
                f'https://{server}.gofile.io/contents/uploadfile',
                files=files,
                timeout=600
            )
        
        result = response.json()
        if result.get('status') == 'ok':
            print("✅ Upload complete!")
            return result['data']['downloadPage']
        else:
            print(f"❌ Upload failed: {result}")
    except Exception as e:
        print(f"❌ Error: {e}")
    
    return None

def upload_rclone(file_path):
    """Upload file via rclone with progress and duplicate handling"""
    file_name = os.path.basename(file_path)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    
    # Build rclone path (handle empty folder)
    if RCLONE_FOLDER:
        rclone_dest = f'{RCLONE_REMOTE}:{RCLONE_FOLDER}'
        base_path = f'{RCLONE_REMOTE}:{RCLONE_FOLDER}'
    else:
        rclone_dest = f'{RCLONE_REMOTE}:'
        base_path = f'{RCLONE_REMOTE}:'
    
    print(f"📤 Uploading via rclone: {file_name} ({file_size_mb:.2f} MB)")
    print(f"   Destination: {rclone_dest}")
    
    try:
        # Check if file already exists and find next available version
        print("   Checking for existing file...")
        original_name = file_name
        name_parts = os.path.splitext(file_name)
        version = 0
        
        while True:
            check_path = f'{base_path}/{file_name}' if base_path.endswith(':') else f'{base_path}/{file_name}'
            check_result = subprocess.run([
                'rclone', 'lsf', check_path
            ], capture_output=True, text=True)
            
            if check_result.returncode == 0 and check_result.stdout.strip():
                # File exists, try next version
                version += 1
                file_name = f"{name_parts[0]} ({version}){name_parts[1]}"
                print(f"   ⚠️  File exists, trying: {file_name}")
            else:
                # File doesn't exist, use this name
                if version > 0:
                    print(f"   ✅ Using versioned name: {file_name}")
                break
        
        # If we need to rename the file locally for upload
        upload_file = file_path
        if file_name != original_name:
            # Create a temporary renamed copy
            temp_dir = os.path.dirname(file_path)
            upload_file = os.path.join(temp_dir, file_name)
            import shutil
            shutil.copy2(file_path, upload_file)
        
        rclone_file_path = f'{base_path}/{file_name}' if base_path.endswith(':') else f'{base_path}/{file_name}'
        
        # Upload file with real-time output
        process = subprocess.Popen([
            'rclone', 'copy', upload_file, rclone_dest,
            '--progress', '--stats', '1s'
        ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        
        # Print progress in real-time
        for line in process.stdout:
            line = line.strip()
            if line and ('Transferred:' in line or '%' in line or 'ETA' in line):
                print(f"   {line}")
        
        process.wait()
        
        # Clean up temp file if we created one
        if upload_file != file_path and os.path.exists(upload_file):
            os.remove(upload_file)
        
        if process.returncode != 0:
            print("❌ Upload failed!")
            return None
        
        print("✅ Upload complete!")
        
        # Get link
        print("Getting shareable link...")
        result = subprocess.run([
            'rclone', 'link', rclone_file_path
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            return result.stdout.strip()
        else:
            return rclone_file_path
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def upload_file(file_path):
    """Smart upload with fallback"""
    # Try rclone first if configured (RCLONE_FOLDER can be empty)
    if RCLONE_REMOTE:
        url = upload_rclone(file_path)
        if url:
            return url
    
    # Fallback to GoFile
    url = upload_gofile(file_path)
    return url if url else "Upload failed"

def find_rom_zip():
    """Find the main ROM zip file"""
    rom_patterns = ['axion-*.zip', 'lineage-*.zip', 'voltage-*.zip', 'arrow-*.zip', 'evolution-*.zip']
    
    for pattern in rom_patterns:
        files = list(Path(OUT_DIR).glob(pattern))
        # Exclude OTA and IMG files
        files = [f for f in files if 'ota' not in f.name.lower() and 'img' not in f.name.lower()]
        # Filter by size >500MB
        files = [f for f in files if f.stat().st_size > 500 * 1024 * 1024]
        if files:
            # Return newest
            return str(max(files, key=lambda f: f.stat().st_mtime))
    
    return None

def handle_interrupt(signum, frame):
    """Handle Ctrl+C interrupt"""
    print("\n⚠️  Build interrupted by user!")
    
    global build_message_id, use_banner, build_process
    
    if build_process:
        build_process.terminate()
    
    if build_message_id:
        interrupt_msg = f"""⚠️ | <i>Build interrupted by user</i>

<b>• ROM:</b> <code>{ROM_NAME}</code>
<b>• DEVICE:</b> <code>{DEVICE}</code>

<i>Build was cancelled</i>"""
        
        if use_banner:
            edit_photo_caption(build_message_id, interrupt_msg)
        else:
            edit_message(build_message_id, interrupt_msg)
    
    # Cleanup
    for f in ['build_banner.png', 'github_avatar.png', 'avatar_circle.png']:
        path = os.path.join(ROOT_DIRECTORY, f)
        if os.path.exists(path):
            os.remove(path)
    
    sys.exit(130)

# ============================================================================
# MAIN
# ============================================================================

def main():
    global OUT_DIR, ANDROID_VERSION, GITHUB_ORG_AVATAR, ROM_NAME
    global build_message_id, use_banner, build_process
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='CI Bot - Automated ROM Build Script')
    parser.add_argument('-s', '--sync', action='store_true', help='Sync sources before building')
    parser.add_argument('-c', '--clean', action='store_true', help='Clean build directory')
    parser.add_argument('--c-d', '--clean-device', action='store_true', help='Clean device directory')
    args = parser.parse_args()
    
    # Setup interrupt handler
    signal.signal(signal.SIGINT, handle_interrupt)
    
    print("🚀 CI Bot - Starting build process...")
    
    # Get ROM info from manifest repository
    print("📄 Getting ROM info from manifest repository...")
    
    manifest_repo = os.path.join(ROOT_DIRECTORY, '.repo/manifests')
    if os.path.exists(manifest_repo):
        try:
            result = subprocess.run(
                ['git', '-C', manifest_repo, 'remote', 'get-url', 'origin'],
                capture_output=True,
                text=True,
                timeout=5
            )
            
            if result.returncode == 0:
                remote_url = result.stdout.strip()
                print(f"📡 Manifest remote: {remote_url}")
                
                # Extract org from GitHub URL
                # Formats: https://github.com/ORG/REPO or git@github.com:ORG/REPO
                match = re.search(r'github\.com[:/]([^/]+)', remote_url)
                if match:
                    github_org = match.group(1)
                    
                    # Use GitHub org as ROM name directly
                    ROM_NAME = github_org
                    GITHUB_ORG_AVATAR = f"https://github.com/{github_org}.png?size=200"
                    
                    print(f"✅ Found ROM: {ROM_NAME}")
                    print(f"🔗 Avatar URL: {GITHUB_ORG_AVATAR}")
        except Exception as e:
            print(f"⚠️  Could not get manifest remote: {e}")
            print(f"⚠️  Using directory name as ROM name: {ROM_NAME}")
    
    # Get Android version from manifest
    def detect_android_version():
        """Detect Android version from .repo/manifests/default.xml"""
        
        # Check .repo/manifests/default.xml for AOSP revision tag
        default_manifest = os.path.join(ROOT_DIRECTORY, '.repo/manifests/default.xml')
        if os.path.exists(default_manifest):
            try:
                with open(default_manifest, 'r') as f:
                    content = f.read()
                    # Look for revision="refs/tags/android-16.0.0_r1" or similar
                    match = re.search(r'revision="refs/tags/android-(\d+)\.', content)
                    if match:
                        return match.group(1)
                    # Also try android-XX.X.X_rX format anywhere in file
                    match = re.search(r'android-(\d+)\.\d+\.\d+', content)
                    if match:
                        return match.group(1)
            except:
                pass
        
        return "Unknown"
    
    ANDROID_VERSION = detect_android_version()
    if ANDROID_VERSION != "Unknown":
        print(f"✅ Found Android version: {ANDROID_VERSION}")
    else:
        print(f"⚠️  Could not detect Android version, using 'Unknown'")
    
    OUT_DIR = os.path.join(ROOT_DIRECTORY, f"out/target/product/{DEVICE}")
    
    # Cleanup old logs
    for log_file in ['out/error.log', 'out/.lock', BUILD_LOG]:
        if os.path.exists(log_file):
            os.remove(log_file)
    
    # Sync if requested
    if args.sync:
        print("📥 Syncing sources...")
        sync_msg_id = send_message(f"""🟡 | <i>Syncing sources!!</i>

<b>• ROM:</b> <code>{ROM_NAME}</code>
<b>• DEVICE:</b> <code>{DEVICE}</code>
<b>• ANDROID VERSION:</b> <code>{ANDROID_VERSION}</code>""")
        
        try:
            subprocess.run(['repo', 'sync', '-c', '--force-sync', '--no-clone-bundle', '--no-tags'], check=True)
            edit_message(sync_msg_id, f"""🟢 | <i>Sources synced!!</i>

<b>• ROM:</b> <code>{ROM_NAME}</code>
<b>• DEVICE:</b> <code>{DEVICE}</code>""")
        except:
            edit_message(sync_msg_id, "🔴 | <i>Sync failed, continuing with build...</i>")
    
    # Clean if requested
    if args.clean:
        print("🗑️  Cleaning out directory...")
        subprocess.run(['rm', '-rf', 'out'], check=False)
    
    # Generate and send banner
    print("📸 Generating build banner...")
    banner_file = generate_build_banner()
    
    if banner_file:
        print("📤 Sending banner to Telegram...")
        caption = f"""<b>🔨 Building {ROM_NAME}</b>

<b>Device:</b> {DEVICE} | <b>Android:</b> {ANDROID_VERSION}
<b>Type:</b> {'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'}

<b>⏳ Status:</b> Initializing build..."""
        
        build_message_id = send_photo(banner_file, caption)
        if build_message_id:
            use_banner = True
            print(f"✅ Banner sent! Message ID: {build_message_id}")
        else:
            use_banner = False
    
    if not use_banner:
        print("📤 Sending text message to Telegram...")
        text = f"""🟡 | <i>Compiling ROM...</i>

<b>• ROM:</b> <code>{ROM_NAME}</code>
<b>• DEVICE:</b> <code>{DEVICE}</code>
<b>• ANDROID VERSION:</b> <code>{ANDROID_VERSION}</code>
<b>• TYPE:</b> <code>{'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'}</code>
<b>• PROGRESS:</b> <code>Initializing...</code>"""
        
        build_message_id = send_message(text)
    
    # Start build
    print("\n" + "=" * 70)
    print("🔨 STARTING BUILD PROCESS")
    print("=" * 70)
    print(f"ROM: {ROM_NAME}")
    print(f"Device: {DEVICE}")
    print(f"Variant: {VARIANT}")
    print(f"Type: {'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'}")
    if ROM_TYPE:
        print(f"ROM Type: {ROM_TYPE}")
    print("=" * 70 + "\n")
    
    # Track build start time
    build_start_time = time.time()
    
    # Source envsetup
    env_cmd = '. build/envsetup.sh'
    
    # Determine build command
    if ROM_TYPE.startswith('axion-'):
        gms_type = ROM_TYPE.split('-')[1]
        gms_variant = 'vanilla' if gms_type == 'vanilla' else f'gms {gms_type}'
        build_cmd = f'{env_cmd} && axion {DEVICE} {VARIANT} {gms_variant} && ax -br'
        print(f"Build command: axion {DEVICE} {VARIANT} {gms_variant} && ax -br")
    else:
        build_cmd = f'{env_cmd} && brunch {DEVICE} {VARIANT}'
        print(f"Build command: brunch {DEVICE} {VARIANT}")
    
    print(f"Log file: {BUILD_LOG}\n")
    
    # Start build process
    with open(BUILD_LOG, 'w') as log_file:
        build_process = subprocess.Popen(
            build_cmd,
            shell=True,
            executable='/bin/bash',
            stdout=log_file,
            stderr=subprocess.STDOUT
        )
    
    # Start log tail thread (for console output)
    tail_thread = Thread(target=tail_build_log, daemon=True)
    tail_thread.start()
    
    # Start progress monitoring thread (for Telegram updates)
    monitor_thread = Thread(target=monitor_progress, daemon=True)
    monitor_thread.start()
    
    # Wait for build to complete
    build_process.wait()
    tail_thread.join(timeout=2)
    monitor_thread.join(timeout=10)
    
    # Calculate build time
    build_end_time = time.time()
    build_duration = int(build_end_time - build_start_time)
    
    # Check if build succeeded
    error_log = 'out/error.log'
    if os.path.exists(error_log) and os.path.getsize(error_log) > 0:
        # Build failed
        print("❌ Build failed!")
        
        fail_msg = f"""<b>❌ {ROM_NAME} Build Failed</b>

<b>Device:</b> {DEVICE} | <b>Android:</b> {ANDROID_VERSION}

<i>Check logs below</i>"""
        
        if use_banner:
            edit_photo_caption(build_message_id, fail_msg)
        else:
            edit_message(build_message_id, fail_msg)
        
        # Send logs
        send_file(error_log, CONFIG_ERROR_CHATID)
        if os.path.exists(BUILD_LOG):
            send_file(BUILD_LOG, CONFIG_ERROR_CHATID)
    else:
        # Build succeeded
        print("✅ Build succeeded!")
        
        # Extract build stats from log (find the highest action count)
        build_stats = "N/A"
        max_actions = 0
        try:
            with open(BUILD_LOG, 'r') as f:
                for line in f:
                    # Look for ninja progress lines like: "[ 99% 11185/11185 5m4s remaining]"
                    match = re.search(r'\[\s*\d+%\s+(\d+)/(\d+)', line)
                    if match:
                        total = int(match.group(2))
                        if total > max_actions:
                            max_actions = total
            
            if max_actions > 0:
                build_stats = f"{max_actions}/{max_actions} actions"
        except:
            pass
        
        # Find ROM zip
        rom_zip = find_rom_zip()
        if not rom_zip:
            print("❌ Could not find ROM zip!")
            return
        
        print(f"📦 Found ROM: {os.path.basename(rom_zip)}")
        rom_filename = os.path.basename(rom_zip)
        
        # Calculate SHA256
        print("🔍 Calculating SHA256...")
        sha256_hash = hashlib.sha256()
        with open(rom_zip, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        sha256sum = sha256_hash.hexdigest()
        
        # Get file size
        size_bytes = os.path.getsize(rom_zip)
        size_gb = size_bytes / (1024**3)
        
        # Format build duration
        hours = build_duration // 3600
        minutes = (build_duration % 3600) // 60
        seconds = build_duration % 60
        
        # Update message to show uploading status
        upload_msg = f"""<b>📤 Uploading Files...</b>

<b>Device:</b> {DEVICE} | <b>Android:</b> {ANDROID_VERSION}
<b>Type:</b> {'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'}

<b>⏳ Status:</b> Uploading ROM zip..."""
        
        if use_banner:
            edit_photo_caption(build_message_id, upload_msg)
        else:
            edit_message(build_message_id, upload_msg)
        
        # Upload ROM
        print("📤 Uploading ROM...")
        rom_url = upload_file(rom_zip)
        
        # Upload boot images only if vendor_boot.img exists
        boot_images = {}
        vendor_boot_path = os.path.join(OUT_DIR, 'vendor_boot.img')
        if os.path.exists(vendor_boot_path):
            # Update message for boot images
            upload_msg = f"""<b>📤 Uploading Files...</b>

<b>Device:</b> {DEVICE} | <b>Android:</b> {ANDROID_VERSION}
<b>Type:</b> {'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'}

<b>⏳ Status:</b> Uploading boot images..."""
            
            if use_banner:
                edit_photo_caption(build_message_id, upload_msg)
            else:
                edit_message(build_message_id, upload_msg)
            
            for img_name in ['vendor_boot.img', 'boot.img', 'init_boot.img']:
                img_path = os.path.join(OUT_DIR, img_name)
                if os.path.exists(img_path):
                    print(f"📤 Uploading {img_name}...")
                    img_url = upload_file(img_path)
                    boot_images[img_name] = img_url
        
        # Build the success message
        success_msg = f"""<b>✅ {ROM_NAME} Build Complete!</b>

<b>Device:</b> {DEVICE} | <b>Android:</b> {ANDROID_VERSION}
<b>Type:</b> {'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'} | <b>Build Type:</b> {VARIANT}

<b>📊 Build Stats:</b>
<b>• Duration:</b> {hours} hour(s), {minutes} minute(s), {seconds} second(s)
<b>• Actions:</b> {build_stats}

<b>🔧 Configuration:</b>
<b>• File:</b> <code>{rom_filename}</code>
<b>• Size:</b> {size_gb:.2f} GiB
<b>• SHA256:</b> <code>{sha256sum}</code>"""
        
        # Create download buttons
        download_buttons = create_download_buttons(rom_url, boot_images if boot_images else None)
        
        if use_banner:
            edit_photo_caption(build_message_id, success_msg, reply_markup=download_buttons)
        else:
            edit_message(build_message_id, success_msg, reply_markup=download_buttons)
        
        # Send build.log
        if os.path.exists(BUILD_LOG):
            send_file(BUILD_LOG)
    
    # Cleanup temporary files
    print("\n🧹 Cleaning up temporary files...")
    for f in ['build_banner.png', 'rom_logo.png', 'logo_circle.png']:
        path = os.path.join(ROOT_DIRECTORY, f)
        if os.path.exists(path):
            os.remove(path)
            print(f"   Removed: {f}")
    
    print("\n" + "=" * 70)
    print("✅ CI Bot completed successfully!")
    print("=" * 70)
    
    # Power off if configured
    if POWEROFF:
        print("\n⚠️  POWEROFF is enabled - shutting down in 10 seconds...")
        print("   Press Ctrl+C to cancel")
        try:
            time.sleep(10)
            print("🔌 Shutting down system...")
            subprocess.run(['sudo', 'poweroff'], check=False)
        except KeyboardInterrupt:
            print("\n⚠️  Shutdown cancelled by user")

if __name__ == "__main__":
    main()
