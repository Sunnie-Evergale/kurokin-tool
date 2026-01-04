# LittleCheese Visual Novel Text Extraction Tools

Tools to extract and translate text from LittleCheese visual novel games.

## Developers

- **Sunnie Evergale** - Lead Developer

[Support on Ko-fi](https://ko-fi.com/sunnieevergale) - Your support is appreciated!

## Quick Start

```bash
# Step 1: Extract all text from game
python3 text_extractor.py [game_dir] [output_dir]

# Step 1.5: Validate extraction (optional but recommended)
python3 audit_extraction.py

# Step 2: Translate the JSON files in extracted_texts/
# - Add "translation" field to translatable entries
# - Keep UTF-8 encoding

# Step 3: Compile translated text back
python3 compiler.py
```

## Features

- **Text Extractor**: Extracts all Japanese text with type classification
  - 102,175 text strings from 1,264 script files
  - JSON output with line grouping and metadata
  - Automatic text type detection (Dialogue, Narration, Sound Effects, etc.)
  - Captures ASCII system codes (sprite refs, hashtags, labels)
- **Audit Script**: Validates extraction quality
  - Detects misclassified text types
  - Flags punctuation in Name Placeholders/Character Names
  - Identifies potential garbage entries
  - Run after extractor changes to ensure quality
- **Compiler**: Simple sequential replacement - replaces text in order
- Smart text scanning approach (no complex bytecode parsing needed)

## Project Structure

```
kurokin-tool/
├── text_extractor.py    # Extract text from game binaries
├── audit_extraction.py  # Validate extraction quality
├── compiler.py          # Compile translations (simple sequential)
├── compiler_smart.py    # Alternative compiler with auto-shortening
├── doc/                 # Technical documentation
│   └── ENGINE_DOCS.md   # Complete binary structure reference
└── extracted_texts/     # Extracted JSON files
    ├── a_001.json
    ├── a_002.json
    └── ...
```

## Usage

### Extract Text

```bash
python3 text_extractor.py [game_directory] [output_directory]
```

Creates JSON files grouped by line number:
```json
{
  "lines": {
    "1": [
      {"type": "Narration", "original": "日常：105", "translation": null},
      {"type": "Dialogue", "original": "「こんにちは」", "translation": null}
    ]
  },
  "metadata": {
    "file": "a_001",
    "total_lines": 50,
    "translatable": 42
  }
}
```

### Translate

Edit JSON files in `extracted_texts/`:
- Add translations to the `"translation"` field
- `"translation": null` entries need translation
- Entries without `"translation"` field are system codes (don't translate)
- Save as UTF-8 encoding

### Compile

```bash
python3 compiler.py [original] [translated] [output]
```

## Text Types

| Type | Translate? | Example |
|------|-----------|---------|
| Dialogue | YES | `「こんにちは」` |
| Narration | YES | Plain descriptive text |
| Inner Thought | YES | `＜そうだね＞` |
| Sound Effect | NO | `設備_部屋ドアOP.wav` |
| Sprite Reference | NO | `ST_N\ikuto_A_1_091` |
| Hashtag Label | NO | `#KANA` |
| Character Name | NO | `郁人` |
| Season/Date Marker | NO | `郁人：X`, `透央：X` |

## Important Notes

⚠️ **Always backup original game files before using compiled scripts!**

### How It Works

The tools use a simple text scanning approach:
1. **Extractor**: Scans binary for Shift-JIS and ASCII patterns
2. **Groups** text by line numbers using newline delimiters
3. **Classifies** each string by type (dialogue, narration, system codes)
4. **Compiler**: Reads translations, replaces strings in sequential order

```
Binary file has: [text1][text2][text3]...
Extracted as JSON:
{
  "lines": {
    "1": [{"original": "text1", "translation": null}],
    "2": [{"original": "text2", "translation": null}]
  }
}

Translate:
{"original": "text1", "translation": "hello"}

Compiled as: [hello][world][test]...
```

## Requirements

- Python 3.6+
- Original game files

## Game Information

- **Developer**: LittleCheese
- **Engine**: Kirikiri2 (KAG) bytecode variant
- **Encoding**: Shift-JIS (SJIS)
- **Files**: 1,264 script binaries

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Text cut off? | Use shorter translations or `compiler_smart.py` |
| Encoding errors? | Remove special characters (™, ©, emoji) |
| Game crashes? | Test with single file first, check file sizes |
| JSON parse error? | Ensure valid JSON syntax after editing |

## Documentation

For technical details, binary structure, opcodes, and reverse engineering findings:

```bash
cat doc/ENGINE_DOCS.md
```

Topics covered:
- Complete binary format analysis
- Text type classification guide
- Sentence splitting and delimiters
- Opcode reference
- Character encoding tables

## License

For fan translation purposes only. Support official releases!
