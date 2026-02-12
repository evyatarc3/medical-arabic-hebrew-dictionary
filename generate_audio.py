#!/usr/bin/env python3
"""
generate_audio.py - Extract Arabic texts from index.html and generate audio files via MimikaStudio.

Prerequisites:
  1. Install MimikaStudio: git clone https://github.com/BoltzmannEntropy/MimikaStudio.git
  2. Run: cd MimikaStudio && ./install.sh
  3. Start server: ./bin/mimikactl up --no-flutter
  4. Run this script: python3 generate_audio.py

The script will:
  - Parse index.html to extract all Arabic texts (vocabulary, dialogues, admin sentences)
  - Send each text to MimikaStudio's Chatterbox Multilingual engine (Arabic)
  - Download the generated WAV files
  - Convert them to MP3 (smaller size, better for web)
  - Save them in an 'audio/' folder with consistent naming
"""

import json
import os
import re
import subprocess
import sys
import time
import hashlib
import urllib.request
import urllib.error

# --- Configuration ---
MIMIKA_BASE_URL = "http://localhost:8000"
CHATTERBOX_ENDPOINT = f"{MIMIKA_BASE_URL}/api/chatterbox/generate"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "audio")
INDEX_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
MANIFEST_FILE = os.path.join(OUTPUT_DIR, "manifest.json")

# TTS parameters
TTS_PARAMS = {
    "language": "ar",
    "voice_name": "Natasha",
    "speed": 0.9,        # Slightly slower for clarity (medical context)
    "temperature": 0.6,  # Lower = more consistent
    "cfg_weight": 1.0,
    "exaggeration": 0.3, # Natural, not dramatic
    "seed": 42,          # Reproducible
    "max_chars": 300,
}


def text_to_id(text):
    """Create a short, filesystem-safe ID from Arabic text."""
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:12]


def extract_arabic_texts(html_path):
    """Extract all Arabic texts from the index.html file."""
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    entries = []
    pair_pattern = re.compile(
        r'hebrew:\s*"([^"]*)".*?arabic:\s*"([^"]*)"',
        re.DOTALL
    )

    # --- 1. Vocabulary words (scoped to vocabularyData block only) ---
    vocab_start = content.find('const vocabularyData = {')
    vocab_end = content.find('const medicalDialogues')
    if vocab_start != -1 and vocab_end != -1:
        vocab_block = content[vocab_start:vocab_end]
        for match in pair_pattern.finditer(vocab_block):
            hebrew = match.group(1).strip()
            arabic = match.group(2).strip()
            if arabic:
                entries.append({
                    "type": "vocabulary",
                    "hebrew": hebrew,
                    "arabic": arabic,
                    "id": text_to_id(arabic),
                    "filename": f"vocab_{text_to_id(arabic)}.mp3"
                })

    # --- 2. Administrative sentences ---
    admin_start = content.find('const administrativeSentences = [')
    if admin_start != -1:
        admin_end = content.find('];', admin_start)
        if admin_end != -1:
            admin_block = content[admin_start:admin_end]
            for match in pair_pattern.finditer(admin_block):
                hebrew = match.group(1).strip()
                arabic = match.group(2).strip()
                if arabic:
                    entries.append({
                        "type": "admin",
                        "hebrew": hebrew,
                        "arabic": arabic,
                        "id": text_to_id(arabic),
                        "filename": f"admin_{text_to_id(arabic)}.mp3"
                    })

    # Deduplicate by Arabic text
    seen = set()
    unique_entries = []
    for entry in entries:
        if entry["arabic"] not in seen:
            seen.add(entry["arabic"])
            unique_entries.append(entry)

    return unique_entries


def check_mimika_server():
    """Check if MimikaStudio server is running."""
    try:
        req = urllib.request.Request(f"{MIMIKA_BASE_URL}/api/chatterbox/info")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status == 200
    except Exception:
        return False


def generate_audio(text, output_path):
    """Generate audio for Arabic text using MimikaStudio Chatterbox."""
    payload = {
        "text": text,
        **TTS_PARAMS
    }

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        CHATTERBOX_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8') if e.fp else ''
        print(f"  HTTP Error {e.code}: {error_body[:200]}")
        return False
    except Exception as e:
        print(f"  Error: {e}")
        return False

    # Download the WAV file
    audio_url = result.get("audio_url", "")
    if not audio_url:
        print(f"  No audio_url in response: {result}")
        return False

    wav_url = f"{MIMIKA_BASE_URL}{audio_url}"
    wav_path = output_path.replace('.mp3', '.wav')

    try:
        urllib.request.urlretrieve(wav_url, wav_path)
    except Exception as e:
        print(f"  Download error: {e}")
        return False

    # Convert WAV to MP3 using ffmpeg (if available)
    try:
        result = subprocess.run(
            ['ffmpeg', '-y', '-i', wav_path, '-codec:a', 'libmp3lame', '-qscale:a', '4', output_path],
            capture_output=True, timeout=30
        )
        if result.returncode == 0:
            os.remove(wav_path)  # Clean up WAV
        else:
            # ffmpeg failed, keep WAV and rename
            final_path = output_path.replace('.mp3', '.wav')
            if wav_path != final_path:
                os.rename(wav_path, final_path)
    except FileNotFoundError:
        # ffmpeg not available, keep WAV
        final_path = output_path.replace('.mp3', '.wav')
        if wav_path != final_path:
            os.rename(wav_path, final_path)
        print("  (ffmpeg not found - keeping WAV format)")
    except Exception:
        if os.path.exists(wav_path):
            final_path = output_path.replace('.mp3', '.wav')
            if wav_path != final_path:
                os.rename(wav_path, final_path)

    return True


def main():
    print("=" * 60)
    print("MimikaStudio Arabic Audio Generator")
    print("for Medical Arabic-Hebrew Dictionary")
    print("=" * 60)

    # Check server
    print("\nChecking MimikaStudio server...")
    if not check_mimika_server():
        print("\nERROR: MimikaStudio server is not running!")
        print("Please start it first:")
        print("  cd ~/MimikaStudio")
        print("  ./bin/mimikactl up --no-flutter")
        sys.exit(1)
    print("Server is running!")

    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Extract texts
    print(f"\nExtracting Arabic texts from {INDEX_HTML}...")
    entries = extract_arabic_texts(INDEX_HTML)
    print(f"Found {len(entries)} unique Arabic texts")
    print(f"  - Vocabulary: {sum(1 for e in entries if e['type'] == 'vocabulary')}")
    print(f"  - Administrative: {sum(1 for e in entries if e['type'] == 'admin')}")

    # Load existing manifest (for resuming)
    manifest = {}
    if os.path.exists(MANIFEST_FILE):
        with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
            manifest = json.load(f)
        print(f"\nResuming: {len(manifest)} files already generated")

    # Generate audio
    total = len(entries)
    generated = 0
    skipped = 0
    failed = 0

    print(f"\nGenerating audio files...")
    print("-" * 60)

    for i, entry in enumerate(entries):
        output_path = os.path.join(OUTPUT_DIR, entry["filename"])

        # Skip if already generated (check both mp3 and wav)
        wav_path = output_path.replace('.mp3', '.wav')
        if entry["id"] in manifest and (os.path.exists(output_path) or os.path.exists(wav_path)):
            skipped += 1
            continue

        print(f"[{i+1}/{total}] {entry['hebrew'][:30]:30s} -> {entry['arabic'][:30]}")

        if generate_audio(entry["arabic"], output_path):
            generated += 1
            # Check if mp3 or wav was created
            actual_filename = entry["filename"]
            if not os.path.exists(output_path) and os.path.exists(wav_path):
                actual_filename = actual_filename.replace('.mp3', '.wav')

            manifest[entry["id"]] = {
                "arabic": entry["arabic"],
                "hebrew": entry["hebrew"],
                "type": entry["type"],
                "filename": actual_filename
            }
            # Save manifest incrementally
            with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        else:
            failed += 1
            print(f"  FAILED!")

        # Small delay to avoid overwhelming the server
        time.sleep(0.5)

    print("-" * 60)
    print(f"\nDone!")
    print(f"  Generated: {generated}")
    print(f"  Skipped (already exists): {skipped}")
    print(f"  Failed: {failed}")
    print(f"  Total in manifest: {len(manifest)}")
    print(f"\nAudio files saved in: {OUTPUT_DIR}")
    print(f"Manifest: {MANIFEST_FILE}")


if __name__ == "__main__":
    main()
