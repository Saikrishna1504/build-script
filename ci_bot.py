#!/usr/bin/env python3
"""
CI Bot - Automated Android ROM Build Script with Telegram Notifications
Optimized Python implementation with built-in banner generation
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
import shutil
from pathlib import Path
from threading import Thread
from io import BytesIO

# Try to import PIL for banner generation
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️  Warning: Pillow not installed. Banner generation disabled.", file=sys.stderr)
    print("   Install with: sudo apt install python3-pil", file=sys.stderr)

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

# Banner Configuration (Optional)
BANNER_THEME = "deepSpace"      # Banner theme: deepSpace, sunset, ocean, forest, matrix, cyberpunk

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

TELEGRAM_BASE_URL = f"https://api.telegram.org/bot{CONFIG_BOT_TOKEN}"

# ============================================================================
# BANNER GENERATOR CLASS
# ============================================================================

class BannerGenerator:
    """Self-hosted banner generator - no external API needed!"""
    
    THEMES = {
        'deepSpace': {
            'gradient_start': '#1a0b2e',
            'gradient_end': '#2d1b4e',
            'accent': '#7b2cbf',
            'text_primary': '#ffffff',
            'text_secondary': '#a8b2d1',
        },
        'sunset': {
            'gradient_start': '#ff6b35',
            'gradient_end': '#f7931e',
            'accent': '#c1121f',
            'text_primary': '#ffffff',
            'text_secondary': '#ffe5d9',
        },
        'ocean': {
            'gradient_start': '#03045e',
            'gradient_end': '#0077b6',
            'accent': '#00b4d8',
            'text_primary': '#ffffff',
            'text_secondary': '#caf0f8',
        },
        'forest': {
            'gradient_start': '#1b4332',
            'gradient_end': '#2d6a4f',
            'accent': '#52b788',
            'text_primary': '#ffffff',
            'text_secondary': '#d8f3dc',
        },
        'matrix': {
            'gradient_start': '#000000',
            'gradient_end': '#0d1b0d',
            'accent': '#00ff00',
            'text_primary': '#00ff00',
            'text_secondary': '#00cc00',
        },
        'cyberpunk': {
            'gradient_start': '#0a0e27',
            'gradient_end': '#1a1a2e',
            'accent': '#ff2e97',
            'text_primary': '#00fff9',
            'text_secondary': '#ff2e97',
        },
    }
    
    def __init__(self, width=1200, height=630):
        self.width = width
        self.height = height
    
    def hex_to_rgb(self, hex_color):
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def create_gradient(self, start_color, end_color):
        """Create a vertical gradient background"""
        base = Image.new('RGB', (self.width, self.height), start_color)
        top = Image.new('RGB', (self.width, self.height), end_color)
        mask = Image.new('L', (self.width, self.height))
        mask_data = []
        for y in range(self.height):
            for x in range(self.width):
                mask_data.append(int(255 * (y / self.height)))
        mask.putdata(mask_data)
        base.paste(top, (0, 0), mask)
        return base
    
    def fetch_avatar(self, avatar_url):
        """Fetch and process avatar image"""
        try:
            response = requests.get(avatar_url, timeout=10)
            if response.status_code == 200:
                avatar = Image.open(BytesIO(response.content))
                return avatar
        except Exception as e:
            print(f"Could not fetch avatar: {e}")
        return None
    
    def create_circular_avatar(self, avatar, size=200):
        """Create circular avatar with glow effect"""
        avatar = avatar.resize((size, size), Image.Resampling.LANCZOS)
        
        # Create circular mask
        mask = Image.new('L', (size, size), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, size, size), fill=255)
        
        # Apply mask
        circular = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        circular.paste(avatar, (0, 0))
        circular.putalpha(mask)
        
        # Create glow effect
        glow_size = size + 40
        glow = Image.new('RGBA', (glow_size, glow_size), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        
        # Draw multiple circles for glow
        for i in range(20, 0, -2):
            alpha = int(255 * (i / 20) * 0.3)
            glow_draw.ellipse(
                (20-i, 20-i, glow_size-20+i, glow_size-20+i),
                fill=(255, 255, 255, alpha)
            )
        
        # Paste circular avatar on glow
        glow.paste(circular, (20, 20), circular)
        return glow
    
    def get_font(self, size, bold=False):
        """Get font with fallback"""
        font_paths = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
        ]
        
        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    return ImageFont.truetype(font_path, size)
                except:
                    pass
        return ImageFont.load_default()
    
    def generate(self, title, avatar_url, theme='deepSpace', device='', version=''):
        """Generate banner image - clean layout with logo, ROM name, device, and Android version"""
        theme_colors = self.THEMES.get(theme, self.THEMES['deepSpace'])
        
        # Create gradient background
        start_rgb = self.hex_to_rgb(theme_colors['gradient_start'])
        end_rgb = self.hex_to_rgb(theme_colors['gradient_end'])
        image = self.create_gradient(start_rgb, end_rgb)
        image = image.convert('RGBA')
        
        overlay = Image.new('RGBA', (self.width, self.height), (255, 255, 255, 0))
        
        # Fetch and add avatar (logo)
        avatar = self.fetch_avatar(avatar_url)
        logo_size = 280
        if avatar:
            circular_avatar = self.create_circular_avatar(avatar, logo_size)
            # Center logo on left side
            avatar_x = 120
            avatar_y = (self.height - circular_avatar.height) // 2
            overlay.paste(circular_avatar, (avatar_x, avatar_y), circular_avatar)
        
        image = Image.alpha_composite(image, overlay)
        image = image.convert('RGB')
        draw = ImageDraw.Draw(image)
        
        # Text position (right side of logo)
        text_start_x = 520
        
        # Draw ROM name (large, bold)
        title_font = self.get_font(90, bold=True)
        title_y = 220
        draw.text((text_start_x, title_y), title.upper(), 
                 fill=theme_colors['text_primary'], font=title_font)
        
        # Draw device and Android version info below ROM name
        info_parts = []
        if device:
            info_parts.append(f"Device: {device}")
        if version:
            info_parts.append(f"Android {version}")
        
        if info_parts:
            info_text = " | ".join(info_parts)
            info_font = self.get_font(36)
            info_y = title_y + 110
            draw.text((text_start_x, info_y), info_text, 
                     fill=theme_colors['text_secondary'], font=info_font)
        
        return image
    
    def save(self, image, output_path):
        """Save generated banner"""
        image.save(output_path, 'PNG', quality=95, optimize=True)
        return output_path

# ============================================================================
# TELEGRAM FUNCTIONS
# ============================================================================

def telegram_request(endpoint, data=None, files=None, timeout=30):
    """Generic Telegram API request handler"""
    url = f"{TELEGRAM_BASE_URL}/{endpoint}"
    try:
        if files:
            response = requests.post(url, data=data, files=files, timeout=timeout)
        else:
            response = requests.post(url, json=data, timeout=timeout)
        result = response.json()
        return result if result.get('ok') else None
    except Exception as e:
        print(f"Telegram API error: {e}", file=sys.stderr)
        return None

def send_message(text, chat_id=None):
    """Send text message to Telegram"""
    data = {
        'chat_id': chat_id or CONFIG_CHATID,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    result = telegram_request('sendMessage', data=data)
    return result['result']['message_id'] if result else None

def send_photo(photo_path, caption, chat_id=None):
    """Send photo with caption to Telegram"""
    with open(photo_path, 'rb') as photo:
        files = {'photo': photo}
        data = {
            'chat_id': chat_id or CONFIG_CHATID,
            'caption': caption,
            'parse_mode': 'HTML'
        }
        result = telegram_request('sendPhoto', data=data, files=files)
        return result['result']['message_id'] if result else None

def send_file(file_path, chat_id=None):
    """Send file to Telegram"""
    with open(file_path, 'rb') as file:
        files = {'document': file}
        data = {'chat_id': chat_id or CONFIG_CHATID, 'parse_mode': 'HTML'}
        result = telegram_request('sendDocument', data=data, files=files, timeout=300)
        return result['result']['message_id'] if result else None

def edit_message(message_id, text, chat_id=None, reply_markup=None):
    """Edit text message"""
    data = {
        'chat_id': chat_id or CONFIG_CHATID,
        'message_id': message_id,
        'text': text,
        'parse_mode': 'HTML',
        'disable_web_page_preview': True
    }
    if reply_markup:
        data['reply_markup'] = reply_markup
    telegram_request('editMessageText', data=data)

def edit_photo_caption(message_id, caption, chat_id=None, reply_markup=None):
    """Edit photo caption"""
    data = {
        'chat_id': chat_id or CONFIG_CHATID,
        'message_id': message_id,
        'caption': caption,
        'parse_mode': 'HTML'
    }
    if reply_markup:
        data['reply_markup'] = reply_markup
    telegram_request('editMessageCaption', data=data)

def create_download_buttons(rom_url, boot_images=None):
    """Create inline keyboard with download buttons"""
    buttons = [[{"text": "📥 Download ROM", "url": rom_url}]]
    
    if boot_images:
        boot_row = []
        for img_name, img_url in boot_images.items():
            button_text = img_name.replace('.img', '').replace('_', ' ').title()
            boot_row.append({"text": button_text, "url": img_url})
            if len(boot_row) == 2:
                buttons.append(boot_row)
                boot_row = []
        if boot_row:
            buttons.append(boot_row)
    
    return {"inline_keyboard": buttons}

# ============================================================================
# BANNER GENERATION
# ============================================================================

def generate_build_banner():
    """Generate build banner (self-hosted only, no API dependency)"""
    output_file = os.path.join(ROOT_DIRECTORY, "build_banner.png")
    
    if not PIL_AVAILABLE:
        print(f"❌ Pillow not installed. Cannot generate banner.")
        print(f"   Install with: sudo apt install python3-pil")
        return None
    
    try:
        print(f"📸 Generating banner...")
        generator = BannerGenerator()
        image = generator.generate(
            title=ROM_NAME,
            avatar_url=GITHUB_ORG_AVATAR if GITHUB_ORG_AVATAR else 'https://avatars.githubusercontent.com/u/0?v=4',
            theme=BANNER_THEME,
            device=DEVICE,
            version=ANDROID_VERSION
        )
        generator.save(image, output_file)
        print(f"✅ Banner generated successfully!")
        return output_file
    except Exception as e:
        print(f"❌ Error generating banner: {e}", file=sys.stderr)
        return None

# ============================================================================
# BUILD FUNCTIONS
# ============================================================================

def fetch_progress():
    """Fetch build progress from build.log"""
    if not os.path.exists(BUILD_LOG):
        return "Initializing..."
    
    try:
        # Read last 100 lines for efficiency
        with open(BUILD_LOG, 'r') as f:
            lines = f.readlines()[-100:]
        
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
                        print(line.rstrip())
            except:
                pass
        time.sleep(0.5)

def monitor_progress():
    """Monitor build progress and update Telegram"""
    global previous_progress
    
    while build_process and build_process.poll() is None:
        current_progress = fetch_progress()
        
        if current_progress != previous_progress:
            print(f"\n🔨 Build Progress: {current_progress}\n", file=sys.stderr)
            
            caption = f"""<b>🔨 Building {ROM_NAME}</b>

<b>Device:</b> {DEVICE} | <b>Android:</b> {ANDROID_VERSION}
<b>Type:</b> {'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'}

<b>⏳ Progress:</b> {current_progress}"""
            
            if use_banner:
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

# ============================================================================
# UPLOAD FUNCTIONS
# ============================================================================

def upload_gofile(file_path):
    """Upload file to GoFile"""
    file_name = os.path.basename(file_path)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    
    print(f"📤 Uploading via GoFile: {file_name} ({file_size_mb:.2f} MB)")
    
    try:
        response = requests.get('https://api.gofile.io/servers', timeout=30)
        server = response.json()['data']['servers'][0]['name']
        print(f"Server: {server}")
        
        print("Uploading to GoFile (this may take a while)...")
        with open(file_path, 'rb') as f:
            response = requests.post(
                f'https://{server}.gofile.io/contents/uploadfile',
                files={'file': f},
                timeout=600
            )
        
        result = response.json()
        if result.get('status') == 'ok':
            print("✅ Upload complete!")
            return result['data']['downloadPage']
        print(f"❌ Upload failed: {result}")
    except Exception as e:
        print(f"❌ Error: {e}")
    return None

def upload_rclone(file_path):
    """Upload file via rclone with duplicate handling"""
    file_name = os.path.basename(file_path)
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    
    rclone_dest = f'{RCLONE_REMOTE}:{RCLONE_FOLDER}' if RCLONE_FOLDER else f'{RCLONE_REMOTE}:'
    base_path = rclone_dest
    
    print(f"📤 Uploading via rclone: {file_name} ({file_size_mb:.2f} MB)")
    print(f"   Destination: {rclone_dest}")
    
    try:
        # Find next available filename
        original_name = file_name
        name_parts = os.path.splitext(file_name)
        version = 0
        
        while True:
            check_path = f'{base_path}/{file_name}'
            result = subprocess.run(['rclone', 'lsf', check_path], capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout.strip():
                version += 1
                file_name = f"{name_parts[0]} ({version}){name_parts[1]}"
                print(f"   ⚠️  File exists, trying: {file_name}")
            else:
                if version > 0:
                    print(f"   ✅ Using versioned name: {file_name}")
                break
        
        # Handle file rename if needed
        upload_file = file_path
        if file_name != original_name:
            upload_file = os.path.join(os.path.dirname(file_path), file_name)
            shutil.copy2(file_path, upload_file)
        
        rclone_file_path = f'{base_path}/{file_name}'
        
        # Upload with progress
        process = subprocess.Popen(
            ['rclone', 'copy', upload_file, rclone_dest, '--progress', '--stats', '1s'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
        )
        
        for line in process.stdout:
            line = line.strip()
            if line and any(x in line for x in ['Transferred:', '%', 'ETA']):
                print(f"   {line}")
        
        process.wait()
        
        # Cleanup temp file
        if upload_file != file_path:
            Path(upload_file).unlink(missing_ok=True)
        
        if process.returncode != 0:
            print("❌ Upload failed!")
            return None
        
        print("✅ Upload complete!")
        
        # Get shareable link
        result = subprocess.run(['rclone', 'link', rclone_file_path], capture_output=True, text=True)
        return result.stdout.strip() if result.returncode == 0 else rclone_file_path
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def upload_file(file_path):
    """Smart upload with fallback"""
    if RCLONE_REMOTE:
        url = upload_rclone(file_path)
        if url:
            return url
    url = upload_gofile(file_path)
    return url if url else "Upload failed"

def find_rom_zip():
    """Find the main ROM zip file"""
    rom_patterns = ['axion-*.zip', 'lineage-*.zip', 'voltage-*.zip', 'arrow-*.zip', 'evolution-*.zip']
    
    for pattern in rom_patterns:
        files = [f for f in Path(OUT_DIR).glob(pattern)
                if 'ota' not in f.name.lower() and 'img' not in f.name.lower()
                and f.stat().st_size > 500 * 1024 * 1024]
        if files:
            return str(max(files, key=lambda f: f.stat().st_mtime))
    return None

def handle_interrupt(signum, frame):
    """Handle Ctrl+C interrupt"""
    print("\n⚠️  Build interrupted by user!")
    
    global build_process
    if build_process:
        build_process.terminate()
    
    if build_message_id:
        msg = f"""⚠️ | <i>Build interrupted by user</i>

<b>• ROM:</b> <code>{ROM_NAME}</code>
<b>• DEVICE:</b> <code>{DEVICE}</code>

<i>Build was cancelled</i>"""
        (edit_photo_caption if use_banner else edit_message)(build_message_id, msg)
    
    # Cleanup
    for f in ['build_banner.png']:
        Path(os.path.join(ROOT_DIRECTORY, f)).unlink(missing_ok=True)
    
    sys.exit(130)

# ============================================================================
# MAIN
# ============================================================================

def clean_rom_name(org_name):
    """Clean ROM name by removing common suffixes"""
    # Remove common suffixes
    suffixes = ['-Staging', '-staging', '-builds', '-Builds', '-android', '-Android', '-AOSP', '-aosp']
    cleaned = org_name
    for suffix in suffixes:
        if cleaned.endswith(suffix):
            cleaned = cleaned[:-len(suffix)]
            break
    return cleaned

def get_rom_info():
    """Get ROM name and avatar from manifest"""
    global ROM_NAME, GITHUB_ORG_AVATAR
    
    manifest_repo = os.path.join(ROOT_DIRECTORY, '.repo/manifests')
    if not os.path.exists(manifest_repo):
        return
    
    try:
        result = subprocess.run(
            ['git', '-C', manifest_repo, 'remote', 'get-url', 'origin'],
            capture_output=True, text=True, timeout=5
        )
        
        if result.returncode == 0:
            remote_url = result.stdout.strip()
            print(f"📡 Manifest remote: {remote_url}")
            
            match = re.search(r'github\.com[:/]([^/]+)', remote_url)
            if match:
                github_org = match.group(1)
                ROM_NAME = clean_rom_name(github_org)
                GITHUB_ORG_AVATAR = f"https://github.com/{github_org}.png?size=200"
                print(f"✅ Found ROM: {ROM_NAME} (from {github_org})")
                print(f"🔗 Avatar URL: {GITHUB_ORG_AVATAR}")
    except Exception as e:
        print(f"⚠️  Could not get manifest remote: {e}")
        print(f"⚠️  Using directory name as ROM name: {ROM_NAME}")

def detect_android_version():
    """Detect Android version from manifest"""
    default_manifest = os.path.join(ROOT_DIRECTORY, '.repo/manifests/default.xml')
    if os.path.exists(default_manifest):
        try:
            with open(default_manifest, 'r') as f:
                content = f.read()
                match = re.search(r'revision="refs/tags/android-(\d+)\.', content)
                if match:
                    return match.group(1)
                match = re.search(r'android-(\d+)\.\d+\.\d+', content)
                if match:
                    return match.group(1)
        except:
            pass
    return "Unknown"

def update_telegram_status(status_msg):
    """Update Telegram message with current status"""
    (edit_photo_caption if use_banner else edit_message)(build_message_id, status_msg)

def main():
    global OUT_DIR, ANDROID_VERSION, build_message_id, use_banner, build_process
    
    # Parse arguments
    parser = argparse.ArgumentParser(description='CI Bot - Automated ROM Build Script')
    parser.add_argument('-s', '--sync', action='store_true', help='Sync sources before building')
    parser.add_argument('-c', '--clean', action='store_true', help='Clean build directory')
    parser.add_argument('--c-d', '--clean-device', action='store_true', help='Clean device directory')
    args = parser.parse_args()
    
    signal.signal(signal.SIGINT, handle_interrupt)
    
    print("🚀 CI Bot - Starting build process...")
    
    # Get ROM info
    print("📄 Getting ROM info from manifest repository...")
    get_rom_info()
    
    ANDROID_VERSION = detect_android_version()
    print(f"{'✅ Found' if ANDROID_VERSION != 'Unknown' else '⚠️  Could not detect'} Android version: {ANDROID_VERSION}")
    
    OUT_DIR = os.path.join(ROOT_DIRECTORY, f"out/target/product/{DEVICE}")
    
    # Cleanup old logs
    for log_file in ['out/error.log', 'out/.lock', BUILD_LOG]:
        Path(log_file).unlink(missing_ok=True)
    
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
        use_banner = bool(build_message_id)
        if use_banner:
            print(f"✅ Banner sent! Message ID: {build_message_id}")
    
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
    print(f"ROM: {ROM_NAME}\nDevice: {DEVICE}\nVariant: {VARIANT}")
    print(f"Type: {'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'}")
    if ROM_TYPE:
        print(f"ROM Type: {ROM_TYPE}")
    print("=" * 70 + "\n")
    
    build_start_time = time.time()
    
    # Build command
    env_cmd = '. build/envsetup.sh'
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
            build_cmd, shell=True, executable='/bin/bash',
            stdout=log_file, stderr=subprocess.STDOUT
        )
    
    # Start monitoring threads
    Thread(target=tail_build_log, daemon=True).start()
    Thread(target=monitor_progress, daemon=True).start()
    
    # Wait for build completion
    build_process.wait()
    build_duration = int(time.time() - build_start_time)
    build_exit_code = build_process.returncode
    
    # Check build result - multiple failure indicators
    error_log = 'out/error.log'
    build_failed = False
    
    # Check 1: Non-zero exit code
    if build_exit_code != 0:
        build_failed = True
        print(f"❌ Build failed with exit code: {build_exit_code}")
    
    # Check 2: Error log exists
    elif os.path.exists(error_log) and os.path.getsize(error_log) > 0:
        build_failed = True
        print("❌ Build failed! (error.log found)")
    
    # Check 3: Look for error patterns in build log
    elif os.path.exists(BUILD_LOG):
        try:
            with open(BUILD_LOG, 'r') as f:
                log_content = f.read()
                error_patterns = ['error:', 'FAILED:', 'Cannot locate', 'fatal:', 'panic:']
                if any(pattern in log_content for pattern in error_patterns):
                    build_failed = True
                    print("❌ Build failed! (errors detected in log)")
        except:
            pass
    
    if build_failed:
        fail_msg = f"""<b>❌ {ROM_NAME} Build Failed</b>

<b>Device:</b> {DEVICE} | <b>Android:</b> {ANDROID_VERSION}
<b>Exit Code:</b> {build_exit_code}

<i>Check logs below</i>"""
        update_telegram_status(fail_msg)
        
        if os.path.exists(error_log):
            send_file(error_log, CONFIG_ERROR_CHATID)
        if os.path.exists(BUILD_LOG):
            send_file(BUILD_LOG, CONFIG_ERROR_CHATID)
    else:
        print("✅ Build succeeded!")
        
        # Extract build stats
        max_actions = 0
        try:
            with open(BUILD_LOG, 'r') as f:
                for line in f:
                    match = re.search(r'\[\s*\d+%\s+(\d+)/(\d+)', line)
                    if match:
                        total = int(match.group(2))
                        if total > max_actions:
                            max_actions = total
        except:
            pass
        
        build_stats = f"{max_actions}/{max_actions} actions" if max_actions > 0 else "N/A"
        
        # Find ROM zip
        rom_zip = find_rom_zip()
        if not rom_zip:
            print("❌ Could not find ROM zip!")
            return
        
        print(f"📦 Found ROM: {os.path.basename(rom_zip)}")
        
        # Calculate SHA256
        print("🔍 Calculating SHA256...")
        sha256_hash = hashlib.sha256()
        with open(rom_zip, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        
        rom_filename = os.path.basename(rom_zip)
        size_gb = os.path.getsize(rom_zip) / (1024**3)
        hours, remainder = divmod(build_duration, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        # Update status - uploading
        update_telegram_status(f"""<b>📤 Uploading Files...</b>

<b>Device:</b> {DEVICE} | <b>Android:</b> {ANDROID_VERSION}
<b>Type:</b> {'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'}

<b>⏳ Status:</b> Uploading ROM zip...""")
        
        print("📤 Uploading ROM...")
        rom_url = upload_file(rom_zip)
        
        # Upload boot images if vendor_boot.img exists
        boot_images = {}
        if os.path.exists(os.path.join(OUT_DIR, 'vendor_boot.img')):
            update_telegram_status(f"""<b>📤 Uploading Files...</b>

<b>Device:</b> {DEVICE} | <b>Android:</b> {ANDROID_VERSION}
<b>Type:</b> {'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'}

<b>⏳ Status:</b> Uploading boot images...""")
            
            for img_name in ['vendor_boot.img', 'boot.img', 'init_boot.img']:
                img_path = os.path.join(OUT_DIR, img_name)
                if os.path.exists(img_path):
                    print(f"📤 Uploading {img_name}...")
                    boot_images[img_name] = upload_file(img_path)
        
        # Final success message
        success_msg = f"""<b>✅ {ROM_NAME} Build Complete!</b>

<b>Device:</b> {DEVICE} | <b>Android:</b> {ANDROID_VERSION}
<b>Type:</b> {'Official' if CONFIG_OFFICIAL_FLAG == '1' else 'Unofficial'} | <b>Build Type:</b> {VARIANT}

<b>📊 Build Stats:</b>
<b>• Duration:</b> {hours} hour(s), {minutes} minute(s), {seconds} second(s)
<b>• Actions:</b> {build_stats}

<b>🔧 Configuration:</b>
<b>• File:</b> <code>{rom_filename}</code>
<b>• Size:</b> {size_gb:.2f} GiB
<b>• SHA256:</b> <code>{sha256_hash.hexdigest()}</code>"""
        
        download_buttons = create_download_buttons(rom_url, boot_images if boot_images else None)
        
        (edit_photo_caption if use_banner else edit_message)(build_message_id, success_msg, reply_markup=download_buttons)
        
        if os.path.exists(BUILD_LOG):
            send_file(BUILD_LOG)
    
    # Cleanup
    print("\n🧹 Cleaning up temporary files...")
    banner_path = Path(os.path.join(ROOT_DIRECTORY, 'build_banner.png'))
    if banner_path.exists():
        banner_path.unlink()
        print(f"   Removed: build_banner.png")
    
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
