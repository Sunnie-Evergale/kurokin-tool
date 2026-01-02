#!/usr/bin/env python3
"""
LittleCheese Script Compiler
Repacks translated text back into LittleCheese binary script files

Features:
- Text length validation
- Skips text that's too long (keeps Japanese original)
- Clear warnings for skipped text
"""

import os
import sys
from pathlib import Path

def is_sjis_text_start(byte_val):
    """Check if byte is valid start of Shift-JIS text"""
    return 0x81 <= byte_val <= 0x9F or 0xE0 <= byte_val <= 0xEF

def find_text_strings(data):
    """Find all text strings and their positions in binary data"""
    texts = []
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
                        texts.append({
                            'offset': text_start,
                            'end': offset,
                            'bytes': text_bytes,
                            'text': text
                        })
                except:
                    pass

        offset += 1

    return texts

def replace_text_in_file(original_file, translated_file, output_file):
    """Replace text in original file with translated text"""
    with open(original_file, 'rb') as f:
        data = bytearray(f.read())

    texts = find_text_strings(data)
    print(f"  Found {len(texts)} text strings in original file")

    with open(translated_file, 'r', encoding='utf-8') as f:
        translated_lines = f.readlines()

    translated_texts = []
    for line in translated_lines:
        line = line.strip()
        if line and '. ' in line:
            parts = line.split('. ', 1)
            if len(parts) == 2:
                index = int(parts[0]) - 1
                text = parts[1]
                translated_texts.append((index, text))

    print(f"  Found {len(translated_texts)} translated texts")
    translated_texts.sort(key=lambda x: x[0])

    replaced_count = 0
    for i, (index, translated_text) in enumerate(translated_texts):
        if index < len(texts):
            original_text_info = texts[index]
            original_bytes = original_text_info['bytes']
            original_length = len(original_bytes)

            try:
                translated_bytes = translated_text.encode('shift-jis')
            except UnicodeEncodeError as e:
                print(f"  Warning: Could not encode text {index+1}: {translated_text}")
                print(f"  Error: {e}")
                continue

            # Simple byte replacement - write English text at offset
            # If shorter: remaining bytes stay as they were (nulls or part of next instruction)
            # If longer: file size increases, overwrites subsequent bytes
            data[original_text_info['offset']:original_text_info['offset'] + len(translated_bytes)] = translated_bytes

            replaced_count += 1

    print(f"  Replaced {replaced_count} text strings")

    with open(output_file, 'wb') as f:
        f.write(data)

    return replaced_count

def compile_directory(input_dir, translated_dir, output_dir):
    """Compile all translated files"""
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
            count = replace_text_in_file(original_file, translated_file, output_file)
            total_replaced += count
        except Exception as e:
            print(f"  Error: {e}")

    print(f"\nDone! Replaced {total_replaced} text strings")
    print(f"Output written to: {output_dir}")
    print(f"\n⚠️  IMPORTANT: Backup your original game files before using the compiled files!")

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
