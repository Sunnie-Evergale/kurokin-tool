#!/usr/bin/env python3
"""
LittleCheese Script Text Extractor with JSON Output
Extracts all Shift-JIS text from LittleCheese game script files, grouped by display unit
Uses newline characters to determine line boundaries (not opcodes)
"""

import json
import os
import sys
from pathlib import Path

def is_sjis_text_start(byte_val):
    """Check if byte is valid start of Shift-JIS text"""
    return 0x81 <= byte_val <= 0x9F or 0xE0 <= byte_val <= 0xEF

def is_ascii_pattern_start(data, offset):
    """Check if position starts with known ASCII pattern (sprite refs, sound effects, etc.)"""
    # Sprite references: ST_N\ or ST_L\
    if offset + 4 < len(data):
        four_bytes = data[offset:offset+4]
        if four_bytes == b'ST_N' or four_bytes == b'ST_L':
            return True
    # Sprite refs without ST_ prefix: name_expression_・position (e.g., kanade_D_2_・079)
    # Detect by looking for _・ pattern (underscore + position char 0x81 0x45)
    if offset + 2 < len(data) and data[offset] == ord('_'):
        if offset + 2 < len(data) and data[offset+1] == 0x81 and data[offset+2] == 0x45:
            return True
    # Sound effects: .wav (case insensitive)
    if offset + 4 < len(data):
        four_bytes = data[offset:offset+4].lower()
        if b'.wav' in four_bytes:
            return True
    # Hashtags: #LABEL
    if data[offset] == ord('#'):
        return True
    # Effect/Background references: EFF\ or BG\
    if offset + 3 < len(data):
        three_bytes = data[offset:offset+3]
        if three_bytes == b'EFF' or three_bytes == b'BG\\':
            return True
    return False

def detect_text_type(text):
    """
    Detect text type based on content patterns only
    Returns: (type_name, translate_flag)

    Matches types documented in ENGINE_DOCS.md
    """
    # System codes (never translate)
    if text.startswith('常：'):
        return ("System Code", False)
    # Season/Date markers: 郁人：X (character_name：X format)
    if '：' in text and len(text) <= 10:
        # Check if it follows the pattern: japanese_name + ： + identifier
        parts = text.split('：')
        if len(parts) == 2:
            name_part = parts[0]
            # If first part is a short Japanese name (2-4 chars)
            if len(name_part) <= 6 and any('\u3000' <= c <= '\u9fff' for c in name_part):
                return ("Season/Date Marker", False)
    if '％名％' in text:
        return ("Name Placeholder", "SPECIAL")
    # Position codes: ・XXX or embedded in sprite refs like kanade_D_2_・079
    if '・' in text:
        # If it has _・ pattern (e.g., kanade_D_2_・079), it's a sprite reference
        if '_・' in text:
            return ("Sprite Reference", False)
        # Otherwise just a position code
        if text.startswith('・'):
            return ("Position Code", False)
    if '.wav' in text.lower():
        return ("Sound Effect", False)
    if text.startswith('ST_N\\') or text.startswith('ST_L\\'):
        return ("Sprite Reference", False)
    if text.startswith('#') and len(text) < 20:
        return ("Hashtag Label", False)
    if text.startswith('EFF\\'):
        return ("Effect Reference", False)
    if text.startswith('BG\\'):
        return ("Background Reference", False)
    if '選択パネル' in text:
        return ("UI Marker", False)

    # Check bracket patterns
    if text.startswith('＜') or text.endswith('＞'):
        return ("Inner Thought", True)

    if text.startswith('『') or text.endswith('』'):
        return ("Email/Text Message", True)

    if text.startswith('「') or text.endswith('」'):
        return ("Dialogue", True)

    # Default to narration for plain text
    return ("Narration", True)

def extract_text_from_file_with_newlines(filepath):
    """Extract text strings with line numbers based on newline characters in binary"""
    with open(filepath, 'rb') as f:
        data = f.read()

    results = []
    offset = 0
    current_line = 1

    while offset < len(data):
        # Check for newline - this marks a new line number
        if data[offset] == 0x0A or data[offset] == 0x0D:
            current_line += 1
            offset += 1
            # Skip consecutive newlines
            while offset < len(data) and (data[offset] == 0x0A or data[offset] == 0x0D):
                offset += 1

            # After newline, check for control sequence (0x01 0x01)
            if offset + 1 < len(data) and data[offset] == 0x01 and data[offset+1] == 0x01:
                # Skip to end marker (0x1a) or next null/newline
                while offset < len(data) and data[offset] not in (0x1a, 0x00, 0x0A, 0x0D):
                    offset += 1
                if offset < len(data) and data[offset] == 0x1a:
                    offset += 1  # Skip past the end marker
                continue

            continue

        # Find potential text start
        if is_sjis_text_start(data[offset]):
            text_start = offset

            # Check if there's ASCII immediately before (like a quote mark) that should be included
            # Scan back up to 10 bytes to find ASCII prefix
            scan_back = offset - 1
            while scan_back >= 0 and scan_back >= offset - 10:
                if data[scan_back] in (0x00, 0x09, 0x0A, 0x0D):  # Stop at delimiters
                    break
                if 0x20 <= data[scan_back] <= 0x7E:  # ASCII printable
                    text_start = scan_back
                    scan_back -= 1
                else:
                    break

            # Skip to end of text to find where it ends
            temp_offset = text_start  # Start from text_start (includes ASCII prefix)
            while temp_offset < len(data):
                if is_sjis_text_start(data[temp_offset]):
                    if temp_offset + 1 < len(data):
                        temp_offset += 2
                    else:
                        break
                elif 0x20 <= data[temp_offset] <= 0x7E or 0xA1 <= data[temp_offset] <= 0xDF:
                    temp_offset += 1
                elif data[temp_offset] == 0x00:
                    break
                elif data[temp_offset] in (0x09, 0x0A, 0x0D):
                    break  # Stop at tab, newline
                else:
                    break

            text_bytes = data[offset:temp_offset]
            if len(text_bytes) >= 2:
                try:
                    text = text_bytes.decode('shift-jis')
                    # Filter out garbage: CJK char + control char only
                    # Strip control chars and check if there's actual content left
                    text_clean = ''.join(c for c in text if ord(c) >= 32 or c in '\n\t')
                    if len(text_clean) >= 2 and any('\u3000' <= c <= '\u9fff' for c in text_clean):
                        text_type, translate = detect_text_type(text_clean)
                        results.append((current_line, text_clean, text_type, translate))
                except:
                    pass

            offset = temp_offset
        elif is_ascii_pattern_start(data, offset):
            # Extract ASCII pattern (sprite refs, sound effects, etc.)
            text_start = offset
            temp_offset = offset

            # For _・ pattern, scan backwards to find sprite name start
            if offset + 2 < len(data) and data[offset] == ord('_') and data[offset+1] == 0x81 and data[offset+2] == 0x45:
                # Scan back to find start of sprite name (after null or start of line)
                scan_back = offset - 1
                while scan_back > 0 and data[scan_back] not in (0x00, 0x0A, 0x0D):
                    # Only include ASCII and underscores for sprite name
                    if 0x20 <= data[scan_back] <= 0x7E:
                        scan_back -= 1
                    else:
                        break
                text_start = scan_back + 1
                temp_offset = offset

            # Find null terminator or newline/tab, including SJIS chars in mixed strings
            while temp_offset < len(data) and data[temp_offset] not in (0x00, 0x09, 0x0A, 0x0D):
                # Skip past SJIS characters
                if is_sjis_text_start(data[temp_offset]):
                    if temp_offset + 1 < len(data):
                        temp_offset += 2
                    else:
                        break
                else:
                    temp_offset += 1
            # Stop at null - don't include it in output
            # (temp_offset now points to 0x00, 0x0A, 0x0D, or end of data)

            text_bytes = data[text_start:temp_offset]
            if len(text_bytes) >= 2:
                try:
                    # Try SJIS decoding for mixed ASCII+SJIS strings (e.g., kanade_D_2_・079)
                    text = text_bytes.decode('shift-jis')
                    # Strip control characters
                    text_clean = ''.join(c for c in text if ord(c) >= 32 or c in '\n\t')
                    # Strip trailing punctuation from hashtags
                    if text_clean.startswith('#'):
                        text_clean = text_clean.rstrip('!?.,。、・')
                    if text_clean:
                        text_type, translate = detect_text_type(text_clean)
                        # Only capture known system code types (not generic ASCII)
                        if text_type in ("Sprite Reference", "Sound Effect", "Hashtag Label",
                                         "Effect Reference", "Background Reference", "Season/Date Marker"):
                            results.append((current_line, text_clean, text_type, translate))
                except:
                    pass

            offset = temp_offset
        else:
            offset += 1

    return results, current_line

def group_by_line(results):
    """Group text strings by line number"""
    if not results:
        return {}, 0

    lines = {}
    max_line = 0

    # Mark character names (short narration before dialogue)
    for i in range(len(results)):
        line_num, text, text_type, translate = results[i]

        # Check if this is a character name (no length limit - allows names with titles like "お兄さん")
        if text_type == "Narration":
            jp_chars = sum(1 for c in text if '\u3000' <= c <= '\u9fff')
            if jp_chars > 0 and i + 1 < len(results):
                next_line, next_text, next_type, _ = results[i + 1]
                if next_line == line_num and "Dialogue" in next_type:
                    text_type = "Character Name"
                    translate = False
                    results[i] = (line_num, text, text_type, translate)

    # Group by line number
    for line_num, text, text_type, translate in results:
        line_key = str(line_num)
        if line_key not in lines:
            lines[line_key] = []

        entry = {"type": text_type, "original": text}

        # Only add translation field for translatable items
        if translate is True:
            entry["translation"] = None

        lines[line_key].append(entry)
        max_line = max(max_line, line_num)

    # Post-processing: Convert Narration to Dialogue ONLY if it's between Dialogue entries (split dialogue)
    # Character Names and other types are not affected
    for line_key in lines:
        entries = lines[line_key]
        for i in range(len(entries)):
            # Only convert Narration if both previous and next entries are Dialogue
            if entries[i]["type"] == "Narration":
                prev_is_dialogue = (i > 0 and entries[i-1]["type"] == "Dialogue")
                next_is_dialogue = (i + 1 < len(entries) and entries[i+1]["type"] == "Dialogue")
                if prev_is_dialogue and next_is_dialogue:
                    entries[i]["type"] = "Dialogue"

    # Post-processing: Handle Name Placeholder entries
    for line_key in lines:
        entries = lines[line_key]
        i = 0
        while i < len(entries):
            if entries[i]["type"] == "Name Placeholder":
                # Check if next entry is Dialogue starting with 「
                # If so, Name Placeholder is a Character Name (speaker label), not part of dialogue
                if (i + 1 < len(entries) and
                    entries[i+1]["type"] == "Dialogue" and
                    entries[i+1]["original"].startswith("「")):
                    # Convert to Character Name instead of merging
                    entries[i]["type"] = "Character Name"
                    i += 1
                # Otherwise merge into adjacent dialogue (％名％ inside dialogue text)
                else:
                    merged = False
                    if i > 0 and entries[i-1]["type"] == "Dialogue":
                        # Merge into previous dialogue
                        entries[i-1]["original"] += entries[i]["original"]
                        entries.pop(i)
                        merged = True
                    elif i + 1 < len(entries) and entries[i+1]["type"] == "Dialogue":
                        # Merge into next dialogue
                        entries[i+1]["original"] = entries[i]["original"] + entries[i+1]["original"]
                        entries.pop(i)
                        merged = True
                    if not merged:
                        i += 1
            else:
                i += 1

    return lines, max_line

def extract_all_texts(input_dir, output_dir):
    """Extract text from all script files"""
    input_path = Path(input_dir)
    output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    files = [f for f in input_path.iterdir() if f.is_file() and '.' not in f.name]
    print(f"Found {len(files)} script files")

    total_texts = 0
    for filepath in sorted(files):
        filename = filepath.name
        print(f"Extracting from: {filename}...")

        try:
            raw_results, total_lines = extract_text_from_file_with_newlines(filepath)
            lines, _ = group_by_line(raw_results)

            if not lines:
                continue

            # Count translatable entries
            translatable = sum(
                1 for line_entries in lines.values()
                for entry in line_entries
                if entry.get('translation') is None
            )

            total_texts += sum(len(line_entries) for line_entries in lines.values())

            output = {
                "lines": lines,
                "metadata": {
                    "file": filename,
                    "total_lines": total_lines,
                    "translatable": translatable
                }
            }

            output_file = output_path / f"{filename}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(output, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"  Error: {e}")
            import traceback
            traceback.print_exc()

    print(f"\nDone! Extracted {total_texts} text strings from {len(files)} files")
    print(f"Output written to: {output_dir}")

def main():
    input_dir = "/mnt/c/Users/sibyo/kurotokin project"
    output_dir = "/mnt/c/Users/sibyo/Desktop/Projects/kurokin-tool/extracted_texts"

    if len(sys.argv) > 1:
        input_dir = sys.argv[1]
    if len(sys.argv) > 2:
        output_dir = sys.argv[2]

    extract_all_texts(input_dir, output_dir)

if __name__ == "__main__":
    main()
