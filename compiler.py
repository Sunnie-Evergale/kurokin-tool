#!/usr/bin/env python3
"""
LittleCheese Script Compiler - Simplified
Replaces Japanese text with English text in binary files
Simple sequential replacement - no offset tracking
"""

import os
import sys
from pathlib import Path

def is_sjis_text_start(byte_val):
    """Check if byte is valid start of Shift-JIS text"""
    return 0x81 <= byte_val <= 0x9F or 0xE0 <= byte_val <= 0xEF

def find_and_replace_text(original_file, translated_file, output_file):
    """Find and replace text strings in order"""
    with open(original_file, 'rb') as f:
        data = bytearray(f.read())

    # First, find all Japanese text strings
    japanese_texts = []
    offsets = []

    offset = 0
    while offset < len(data):
        if is_sjis_text_start(data[offset]):
            text_start = offset
            offset += 1
            while offset < len(data):
                if is_sjis_text_start(data[offset]):
                    if offset + 1 < len(data):
                        offset += 2
                    else:
                        break
                elif 0x20 <= data[offset] <= 0x7E or 0xA1 <= data[offset] <= 0xDF:
                    offset += 1
                elif data[offset] == 0x00:
                    break
                else:
                    break

            text_bytes = data[text_start:offset]
            if len(text_bytes) >= 2:
                try:
                    text = text_bytes.decode('shift-jis')
                    if any('\u3000' <= c <= '\u9fff' for c in text):
                        japanese_texts.append(text_bytes)
                        offsets.append(text_start)
                except:
                    pass

        offset += 1

    print(f"  Found {len(japanese_texts)} text strings")

    # Read translations
    with open(translated_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    translations = []
    for line in lines:
        line = line.strip()
        if line and '. ' in line:
            parts = line.split('. ', 1)
            if len(parts) == 2:
                translations.append(parts[1])

    print(f"  Found {len(translations)} translations")

    # Replace in order
    replaced = 0
    for i, (offset, original_bytes) in enumerate(zip(offsets, japanese_texts)):
        if i < len(translations):
            translated_text = translations[i]
            try:
                translated_bytes = translated_text.encode('shift-jis')
                # Simple replacement at offset
                data[offset:offset + len(translated_bytes)] = translated_bytes
                replaced += 1
            except:
                pass

    print(f"  Replaced {replaced} text strings")

    with open(output_file, 'wb') as f:
        f.write(data)

    return replaced

def compile_directory(input_dir, translated_dir, output_dir):
    """Compile all files"""
    input_path = Path(input_dir)
    translated_path = Path(translated_dir)
    output_path = Path(output_dir)

    output_path.mkdir(parents=True, exist_ok=True)

    translated_files = list(translated_path.glob('*_text.txt'))
    print(f"Found {len(translated_files)} translated text files")

    total_replaced = 0
    for translated_file in sorted(translated_files):
        base_name = translated_file.stem.replace('_text', '')
        original_file = input_path / base_name
        output_file = output_path / base_name

        if not original_file.exists():
            print(f"Warning: Original file not found: {base_name}")
            continue

        print(f"Compiling: {base_name}...")
        try:
            count = find_and_replace_text(original_file, translated_file, output_file)
            total_replaced += count
        except Exception as e:
            print(f"  Error: {e}")

    print(f"\nDone! Replaced {total_replaced} text strings")
    print(f"Output written to: {output_dir}")

def main():
    input_dir = "/mnt/c/Users/sibyo/kurotokin project"
    translated_dir = "/mnt/c/Users/sibyo/Desktop/Projects/kurokin-tool/extracted_texts"
    output_dir = "/mnt/c/Users/sibyo/Desktop/Projects/kurokin-tool/compiled_scripts"

    if len(sys.argv) > 1:
        input_dir = sys.argv[1]
    if len(sys.argv) > 2:
        translated_dir = sys.argv[2]
    if len(sys.argv) > 3:
        output_dir = sys.argv[3]

    compile_directory(input_dir, translated_dir, output_dir)

if __name__ == "__main__":
    main()
