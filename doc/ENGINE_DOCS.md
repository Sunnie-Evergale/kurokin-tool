# LittleCheese Engine Documentation

Technical documentation for the LittleCheese visual novel script engine and translation tools.

## Table of Contents

1. [Reverse Engineering Findings](#reverse-engineering-findings)
2. [Script File Structure](#script-file-structure)
3. [Script Parts Explained](#script-parts-explained)
4. [Text Extraction](#text-extraction)
5. [JSON Output Format](#json-output-format)
6. [Script Recompilation](#script-recompilation)
7. [Text Length Solutions](#text-length-solutions)
8. [Sample Input/Output](#sample-inputoutput)
9. [Opcode Reference](#opcode-reference)
10. [Troubleshooting](#troubleshooting)

---

## Reverse Engineering Findings

### Initial Analysis

When examining the game files, I discovered:

1. **File Structure**: 1,264 binary files without extensions
2. **File Format**: Kirikiri2 (KAG) bytecode variant used by LittleCheese
3. **Text Encoding**: Shift-JIS (SJIS) encoding for Japanese text
4. **Total Text**: 101,588 text strings extracted (final accurate count after all post-processing)

### Decompilation Journey

#### Step 1: Identifying the Bytecode Format

Looking at the hex dump of `__c_001`:

```
00000000: 0852 3d42 0030 0100 0a21 2140 635f 3030  .R=B.0...!!@c_00
00000010: 3100 032e 0d0b 245b 8400 b400 0000 4600  1.....$[......F.
00000020: 2e24 0000 0000 82bb 82a4 8141 82c5 82b7  .$.........A....
```

I identified key patterns:
- `08 52 3d` - Register operation ("R=")
- `0a 21 21 40` - Label marker ("!!@")
- `0b 24` or `0b 2e` - Text display opcodes
- Japanese text bytes: `82 bb 82 a4...` = "そう..."

#### Step 2: Text Decoding

First successful text decode:

```
Bytes: 82 bb 82 a4 81 41 82 c5 82 b7 82 e6 82 cb 81 63 81 63
Decoded: そう、ですよね…… (Yes, that's right...)
```

This confirmed Shift-JIS encoding.

#### Step 3: Opcode Analysis

Through systematic analysis, I mapped the opcodes:

| Offset | Bytes | Meaning |
|--------|-------|---------|
| 0-7 | `08 52 3d 42 00 30 01 00` | Register initialization |
| 8-17 | `0a 21 21 40 63 5f 30 30 31 00` | Label "@c_001" |
| 18-20 | `03 2e 0d` | Wait for click command |
| 21+ | `0b 24 [params] [text] 00` | Text display |

#### Step 4: Variable-Length Parameters

**Challenge**: Text instructions had variable parameter lengths (15-16 bytes).

**Pattern discovered**:
```
00 2e 24 00 00 00 00 + SJIS text
```

**Solution**: Pattern matching scan instead of fixed byte offsets.

#### Step 5: Offset Tracking Bug

**Bug**: After processing 0x03 command, offset was incorrectly incremented.

**Root cause**: Missing `continue` statement caused fall-through.

**Fix**: Added `continue` after command processing.

#### Step 6: False Positive Detection

**Bug**: Parameter byte `0x84` was misidentified as SJIS text start.

**Solution**: Pattern matching + CJK character validation.

#### Step 7: ASCII Pattern Detection Bug

**Bug**: Pure ASCII system codes were being skipped because the extractor only looked for Shift-JIS text.

**Root cause**: The `is_sjis_text_start()` function only detected bytes 0x81-0x9F or 0xE0-0xEF, missing:
- Sprite references: `ST_N\ikuto_A_1_102`, `ST_L\L_kotoko_A_1_025`
- Sound effects: `設備_部屋ドアOP.wav`
- Hashtag labels: `#KANA`, `#yuki`
- Effect references: `EFF\フラッシュ２`
- Background references: `BG\bg_001`

**Example from y_010a5 line 13**:
```
Binary: ST_L\L_yukio_C_3_059 透央 「......何で、
Before: Only captured 透央 and dialogue (SJIS strings)
After:  Captured sprite ref + character name + dialogue
```

**Solution**: Added `is_ascii_pattern_start()` function to detect ASCII patterns:

```python
def is_ascii_pattern_start(data, offset):
    """Check if position starts with known ASCII pattern"""
    # Sprite references: ST_N\ or ST_L\
    if offset + 4 < len(data):
        four_bytes = data[offset:offset+4]
        if four_bytes == b'ST_N' or four_bytes == b'ST_L':
            return True
    # Sound effects: .wav
    if offset + 4 < len(data) and b'.wav' in data[offset:offset+4]:
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
```

**Results**:
- Text count increased from 84,839 → 101,100 (+16,261)
- Captured 23,356 ASCII system codes:
  - 6,778 Sprite References
  - 1,996 Sound Effects
  - 11,078 Hashtag Labels
  - 11 Effect References
  - 3,493 Background References

#### Step 8: Sprite Reference + Position Code Split Bug

**Bug**: Sprite references with position codes like `kanade_D_2_・079` were being split into separate entries.

**Example from y_010a5 line 5**:
```
Binary: kanade_D_2_・079 (single string with ASCII + SJIS position)
Before: {"type": "Position Code", "original": "・079"} (missing sprite name)
After:  {"type": "Sprite Reference", "original": "kanade_D_2_・079"} (combined)
```

**Root cause**: The `_・` pattern (underscore + position char) wasn't being detected as a sprite reference.

**Solution**:
1. Added `_・` pattern detection to `is_ascii_pattern_start()`
2. When detected, scan backwards to find sprite name start
3. Extract full string using Shift-JIS decoding for mixed ASCII+SJIS
4. Updated `detect_text_type()` to recognize `_・` pattern as Sprite Reference

```python
# Detect _・ pattern (underscore + position char 0x81 0x45)
if offset + 2 < len(data) and data[offset] == ord('_'):
    if offset + 2 < len(data) and data[offset+1] == 0x81 and data[offset+2] == 0x45:
        return True

# In detect_text_type():
if '・' in text:
    if '_・' in text:  # e.g., kanade_D_2_・079
        return ("Sprite Reference", False)
```

**Results**:
- Text count increased from 101,100 → 106,759 (+5,659 combined sprite refs)
- Sprite references now captured as single entries

#### Step 9: Control Sequence and Tab Handling Bugs

**Bug 1**: Control sequences at line starts were being extracted as garbage entries.

**Example from y_010a5 line 5**:
```
Hex: 01 01 00 00 9f 8e 01 00 9b f8 fd 11 1a ...
      └────control sequence───┘   └end┘
Garbage extracted: "沁\u0001" (CJK char + control byte)
```

**Bug 2**: Hashtags included tab characters: `#yuki\t` instead of `#yuki`.

**Bug 3**: Hashtags with tabs captured following Japanese text as part of the hashtag.

**Solution 1 - Skip control sequences**:
After each newline, check for `0x01 0x01` pattern and skip to `0x1a`:

```python
if data[offset] == 0x0A or data[offset] == 0x0D:
    current_line += 1
    offset += 1
    # Skip consecutive newlines
    while offset < len(data) and (data[offset] == 0x0A or data[offset] == 0x0D):
        offset += 1

    # Check for control sequence (0x01 0x01 ... 0x1a)
    if offset + 1 < len(data) and data[offset] == 0x01 and data[offset+1] == 0x01:
        while offset < len(data) and data[offset] not in (0x1a, 0x00, 0x0A, 0x0D):
            offset += 1
        if offset < len(data) and data[offset] == 0x1a:
            offset += 1
        continue
```

**Solution 2 - Stop at tab (0x09)**:
Added `0x09` to stop conditions for both SJIS and ASCII extraction:

```python
# For SJIS extraction
elif data[temp_offset] in (0x09, 0x0A, 0x0D):
    break  # Stop at tab, newline

# For ASCII extraction
while temp_offset < len(data) and data[temp_offset] not in (0x00, 0x09, 0x0A, 0x0D):
```

**Results**:
- Text count decreased from 106,759 → 102,169 (-4,590 garbage entries removed)
- Hashtags clean: `#yuki` instead of `#yuki\t`
- Control sequences properly skipped

#### Step 10: Text Truncation Bug (ASCII Prefix)

**Bug**: Text was being truncated at the start when preceded by ASCII characters.

**Example from a_014k line 65**:
```
Binary has: %\x00'\x09ああ、琴子がたぶん何かしたんだ……。
Extracted:    、琴子がたぶん何かしたんだ……。
Missing:     ああ、
```

The text `ああ、琴子がたぶん何かしたんだ……。` exists in binary, but extraction started at `、` instead of `ああ`.

**Root cause**:
```
Hex: 25002709 828a0828a08141...
     %  null ' tab  あ     あ    、
```
1. After `%` and null, there's ASCII `'` (0x27)
2. SJIS scanner skips ASCII characters when looking for text start
3. When scanner hits `、` (SJIS 0x81 0x41), it starts extraction there
4. Result: `ああ` before `、` is lost

**Solution**: Scan back up to 10 bytes when SJIS text is found to include ASCII prefix:

```python
if is_sjis_text_start(data[offset]):
    text_start = offset

    # Check if there's ASCII immediately before (like a quote)
    scan_back = offset - 1
    while scan_back >= 0 and scan_back >= offset - 10:
        if data[scan_back] in (0x00, 0x09, 0x0A, 0x0D):  # Stop at delimiters
            break
        if 0x20 <= data[scan_back] <= 0x7E:  # ASCII printable
            text_start = scan_back
            scan_back -= 1
        else:
            break
```

**Results**: 102,169 → 102,227 (+58 previously truncated entries)

#### Step 11: Name Placeholder Merge Bug

**Bug**: Name Placeholder (`％名％`) appearing inside dialogue was being kept as a separate entry instead of merged with the dialogue.

**Example from a_015 line 19**:
```
Before: [
  {"type": "Name Placeholder", "original": "％名％"},
  {"type": "Dialogue", "original": "、黒板に書いて"}
]

After: [
  {"type": "Dialogue", "original": "％名％、黒板に書いて"}
]
```

**Root cause**: Name Placeholders adjacent to dialogue should be part of the dialogue text since they represent player name substitution within spoken lines.

**Solution**: Post-processing to merge Name Placeholder entries into adjacent Dialogue on same line:

```python
# Merge Name Placeholder into adjacent Dialogue
for line_key in lines:
    entries = lines[line_key]
    i = 0
    while i < len(entries):
        if entries[i]["type"] == "Name Placeholder":
            merged = False
            if i > 0 and entries[i-1]["type"] == "Dialogue":
                entries[i-1]["original"] += entries[i]["original"]
                entries.pop(i)
                merged = True
            elif i + 1 < len(entries) and entries[i+1]["type"] == "Dialogue":
                entries[i+1]["original"] = entries[i]["original"] + entries[i+1]["original"]
                entries.pop(i)
                merged = True
            if not merged:
                i += 1
        else:
            i += 1
```

**Results**: 102,229 → 101,356 (-873 merged entries)

#### Step 12: Character Name Detection Improvements

**Bug 1**: Long character names with titles (e.g., "ヒーローお兄さん", 8 chars) were not being detected as Character Names due to length limit.

**Bug 2**: Name Placeholder (`％名％`) appearing BEFORE dialogue was incorrectly being merged into dialogue instead of treated as a Character Name (speaker label).

**Examples**:
```
Before: [
  {"type": "Dialogue", "original": "ヒーローお兄さん", "translation": null},  # Wrong!
  {"type": "Dialogue", "original": "「text」"}
]

After: [
  {"type": "Character Name", "original": "ヒーローお兄さん"},  # Correct!
  {"type": "Dialogue", "original": "「text」", "translation": null}
]
```

```
Before: [
  {"type": "Dialogue", "original": "％名％「智臣さん……？」", "translation": null}  # Merged
]

After: [
  {"type": "Character Name", "original": "％名％"},  # Speaker label
  {"type": "Dialogue", "original": "「智臣さん……？」", "translation": null}
]
```

**Root causes**:
1. Length limit of `len(text) <= 6` excluded longer names
2. Post-processing merged ALL Name Placeholders into adjacent dialogue
3. Binary evidence: `%<name>` pattern (no closing `%`) indicates character name marker

**Solutions**:
1. Removed length limit - any Japanese text before dialogue becomes Character Name
2. Added Name Placeholder check: if followed by dialogue with `「`, convert to Character Name
3. Fixed post-processing to only convert Narration to Dialogue if BETWEEN dialogue entries

**Final accurate count: 101,356 text strings**

#### Step 13: Garbage Entry Removal

**Bug**: Very short Narration entries (garbage like "豐_") appearing on lines with Dialogue.

**Example from y_007d line 2**:
```
Before: [
  {"type": "Narration", "original": "豐_", "translation": null},  # Garbage!
  {"type": "Name Placeholder", "original": "％名％"},
  {"type": "Dialogue", "original": "「......会いたい」", "translation": null}
]

After: [
  {"type": "Character Name", "original": "％名％"},
  {"type": "Dialogue", "original": "「......会いたい」", "translation": null}
]
```

**Root cause**: Extraction was picking up corrupted/partial text (1-2 characters) that should be filtered out. User rule: "once its dialogue, no narration should exist" on that line.

**Solution**: Remove any Narration entries with ≤2 characters from lines that have Dialogue.

**Result**: 101,356 → 101,527 (+179 entries, due to more Name Placeholders kept as Character Names)
**Final accurate count: 101,527 text strings**

#### Step 14: Name Placeholder Punctuation Filter

**Bug**: Name Placeholders containing punctuation were being incorrectly converted to Character Name.

**Example from a_006c line 112**:
```
Before: [
  {"type": "Character Name", "original": "琴子"},
  {"type": "Dialogue", "original": "「あっという間だよ。そもそも一緒に住むって"},
  {"type": "Character Name", "original": "　ことは――――あっ、％名％は弟くんと一緒"},  # Wrong!
  {"type": "Dialogue", "original": "　に住んでるから免疫があるね」"}
]

After: [
  {"type": "Character Name", "original": "琴子"},
  {"type": "Dialogue", "original": "「あっいう間だよ。そもそも一緒に住むって　ことは――――あっ、％名％は弟くんと一緒"},
  {"type": "Dialogue", "original": "　に住んでるから免疫があるね」"}
]
```

**Root cause**: Post-processing was converting ALL Name Placeholders on dialogue lines to Character Names, without checking if the Name Placeholder text itself contained punctuation. Entries like `　ことは――――あっ、％名％は弟くんと一緒` (which has `―` punctuation and is clearly dialogue content) were being misclassified.

**Solution**: Added punctuation filter to Name Placeholder post-processing:
- Clean Name Placeholder (no punctuation/brackets) → Character Name
- Dirty Name Placeholder (has punctuation/brackets) → Merge into adjacent dialogue

**Result**: False positives eliminated. Dialogue text containing name placeholders is now correctly merged into dialogue entries.

#### Step 15: Name Placeholder Sentence Detection

**Bug**: Full sentences containing `％名％` were being classified as Name Placeholder instead of Narration.

**Example from eyes_y008 line 17**:
```
Before:
  {"type": "Name Placeholder", "original": "％名％のことも、二人の関係も。"}

After:
  {"type": "Narration", "original": "％名％のことも、二人の関係も。", "translation": null}
```

**Root cause**: The `detect_text_type()` function immediately classified ANY text containing `％名％` as "Name Placeholder" without checking if it was actually a full sentence. The post-processing logic couldn't fix this because the entry was already misclassified at the initial detection stage.

**Solution**: Updated `detect_text_type()` to only classify short, clean strings as Name Placeholder:
- `％名％` alone (≤4 chars, no punctuation) → Name Placeholder
- `％名％のことも、二人の関係も。` (has `。`, longer text) → Falls through to Narration/Dialogue detection

**Result**: 101,527 → 101,588 (+61 entries, full sentences with name placeholders now get translation field)

### Final Solution: Text Scanning

Instead of full bytecode parsing, implemented a simpler scanning approach:

```python
def extract_text_from_file(filepath):
    data = read_file(filepath)
    texts = []
    offset = 0

    while offset < len(data):
        # Find SJIS text start (0x81-0x9F or 0xE0-0xEF)
        if is_sjis_start(data[offset]):
            text_start = offset
            # Find text end (null terminator)
            while offset < len(data) and data[offset] != 0x00:
                if is_sjis_start(data[offset]):
                    offset += 2
                else:
                    offset += 1
            # Decode and validate
            text = data[text_start:offset].decode('shift-jis')
            if contains_cjk(text):
                texts.append(text)
        offset += 1

    return texts
```

**Benefits**:
- ✅ Doesn't require perfect opcode parsing
- ✅ Finds all text regardless of instruction format
- ✅ Works across different file versions
- ✅ Extracted 101,588 text strings successfully (final accurate count)

### Key Insights

1. **Pattern over Structure**: Scanning for SJIS patterns was more reliable than bytecode parsing
2. **Encoding First**: Shift-JIS identification was the key breakthrough
3. **Validation Matters**: CJK character validation filters false positives
4. **Simple over Complex**: Text scanning was simpler but more effective
5. **ASCII + SJIS**: Must scan for both ASCII patterns and SJIS text to capture all system codes
6. **Mixed Strings**: Some strings combine ASCII + SJIS (e.g., `kanade_D_2_・079`) - use SJIS decoding
7. **Control Sequences**: Binary contains control sequences (`0x01 0x01 ... 0x1a`) that must be skipped
8. **Tab Delimiters**: ASCII patterns like hashtags end with tabs (0x09), must stop there to avoid capturing extra text
9. **ASCII Prefix**: When SJIS text is preceded by ASCII (like quotes), scan back to include it in extraction
10. **Post-Processing**: After extraction, group entries by line and handle special cases
11. **Character Names**: No length limit - names with titles like "ヒーローお兄さん" are valid
12. **Name Placeholder Rules**: Before dialogue = Character Name; inside dialogue = merge
13. **Garbage Filter**: Remove very short Narration (≤2 chars) from lines with Dialogue
14. **Name Placeholder Punctuation**: Name Placeholders with punctuation/brackets are dialogue content, not speaker labels - merge them
15. **Name Placeholder Sentences**: Full sentences with `％名％` embedded are narration/dialogue, not name placeholders
16. **Quality Assurance**: Always run `audit_extraction.py` after modifying `text_extractor.py` to catch regressions

---

## Script File Structure

### Technical Specifications

| Property | Value |
|----------|-------|
| **Engine** | Kirikiri2 (KAG) |
| **Bytecode Format** | LittleCheese variant |
| **Text Encoding** | Shift-JIS (SJIS) |
| **Endianness** | Little-endian |
| **Script Files** | No extension, binary format |

### Character Encoding

Shift-JIS text uses:
- **Double-byte characters**: 0x81-0x9F, 0xE0-0xEF (first byte)
- **ASCII**: 0x20-0x7E
- **Half-width Katakana**: 0xA1-0xDF
- **Null terminator**: 0x00

### Binary Layout

```
Offset 0-7:     Register Initialization
Offset 8-17:    Entry Point Label (@name)
Offset 18+:     Script Instructions
```

### Annotated Hex Dump

```
00000000: 0852 3d42 0030 0100 0a21 2140 635f 3030  .R=B.0...!!@c_00
         └─Register─┘    └─!!@─┘c_001┘

00000010: 3100 032e 0d0b 245b 8400 b400 0000 4600  1.....$[......F.
                     └─┘   └──15 byte params───┘

00000020: 2e24 0000 0000 82bb 82a4 8141 82c5 82b7  .$.........A....
                     └────Shift-JIS Text─────┘

00000030: 82e6 82cb 8163 8163 0040 5f5f 635f 3030  .....c.c.@__c_00
         └─Text end─┘└─Jump to label─┘
```

---

## Script Parts Explained

### 1. File Naming Convention

| Pattern | Meaning | Example |
|---------|---------|---------|
| `__c_XXX` | Chihiro character route | `__c_001`, `__c_002` |
| `__i_XXX` | Ikuto character route | `__i_001`, `__i_002` |
| `__t_XXX` | Tomoomi character route | `__t_001`, `__t_002` |
| `__y_XXX` | Yukio character route | `__y_001`, `__y_002` |
| `__a_XXX` | Common/All routes | `__a_001`, `__a_002` |
| `__end_XXX` | Ending scenes | `__end_c_best` |
| `__eyes_XXX` | Character eye expressions | `__eyes_c001` |
| `MemoryXX` | Memory/Save point references | `Memory01` |
| `NewGame` | New game initialization | `NewGame` |
| `RegTbl` | Registration table | `RegTbl` |

### 2. Script Sections

#### Header Section (Bytes 0-17)
```
0x08 0x52 0x3d [reg] [val] [0] [0]  ← Register init
0x0A 0x21 0x21 0x40 [label] 0x00    ← Entry label
```

#### Text Display Instructions
```
0x0B 0x24/0x2E [15-16 bytes params] [Shift-JIS text] 0x00
```

#### Control Flow
- **Wait**: `0x03 0x2E 0x0D [4 bytes]`
- **Goto**: `0x0E [label] 0x00`
- **Function call**: `0x0D [count] [name] 0x00`

### 3. Embedded Elements

#### Sound Effects (.wav references)

The game scripts reference sound files that play at specific moments:

| Category | Japanese | Purpose | Examples |
|----------|----------|---------|----------|
| 動作 | Dōsa | Movement/actions | `動作_ベッドに落ちる.wav` (falling on bed) |
| 足音 | Ashioto | Footsteps | `足音_スリッパ_リノリウム_R.wav` (slippers on floor) |
| 設備 | Setsubi | Equipment/facilities | `設備_部屋ドアOP.wav` (room door open) |
| 衣類 | Irui | Clothing sounds | `衣類_衣擦れ.wav` (clothes rustling) |
| 環境 | Kankyō | Environmental | `環境_朝チュン.wav` (morning alarm) |
| 電気 | Denki | Electrical | `電気_携帯メール受信.wav` (email received) |
| 台所 | Daidokoro | Kitchen | `台所_食器カチャカチャ_1.wav` (dishes clattering) |
| 雑貨 | Zakkō | Miscellaneous items | `雑貨_景品ベル.wav` (prize bell) |
| 夢 | Yume | Dream scenes | `夢_着地.wav` (landing in dream) |
| システム | Shisutemu | System sounds | `システム_決定.wav` (confirm) |
| 学校 | Gakkō | School environment | Various school sounds |
| 娯楽 | Goraku | Entertainment | Karaoke, game sounds |
| カラオケ | Karaoke | Karaoke specifically | Karaoke-related sounds |
| ダンス | Dansu | Dance scenes | Dance-related sounds |
| エロス | Erosu | Adult scenes | H-scene sounds |
| 水道 | Suidō | Water/plumbing | Water sounds |
| 鍵 | Kagi | Keys/locks | Lock/unlock sounds |
| 鼓動 | Kodō | Heartbeat | Heart sounds |

**Format:** `[Category]_[Action]_[Variant].wav`

#### Text Elements

| Type | Format | Example | Purpose |
|------|--------|---------|---------|
| Dialogue | `「Text」` | `「姉貴は寝てんだっつーの！」` | Character speech |
| Character Name | `Name` | `郁人` | Speaker identifier |
| Narration | Plain text | `何だかリビングの方がうるさい。` | Description/narration |
| Name Placeholder | `％名％` | `％名％` | Player's name insertion |

#### Sprite References

Two formats for character sprite files displayed during dialogue.

**Format 1: `ST_N\*` (with prefix)**

| Format | Pattern | Examples |
|--------|---------|----------|
| `ST_N\<char>_<type>_<expr>_<id>` | Sprite file path | `ST_N\ikuto_B_1_091`, `ST_N\yukio_A_1_141` |

**Character codes:**
- `ikuto` - 郁人 protagonist
- `yukio` - 透央 character

**Type codes:**
- `A` - Main sprite
- `B` - Alternative sprite

**Format 2: `<char>_*` (direct name)**

| Format | Pattern | Examples |
|--------|---------|----------|
| `<char>_<type>_<expr>_<id>` | Direct sprite reference | `kanade_A_1_E017`, `kanade_E_1_E044` |

**Character codes:**
- `kanade` - 奏 character

**Expression codes:**
- `E017`, `E044`, `E078`, etc. - Expression/variant IDs

**Examples from binary:**
```
ST_N\ikuto_B_1_091    (Ikuto, pose B, expression 1, variant 091)
kanade_A_1_E017       (Kanade, type A, expression 1, variant E017)
kanade_E_1_E044       (Kanade, type E, expression 1, variant E044)
kanade_A_2_E038       (Kanade, type A, expression 2, variant E038)
```

**Do NOT translate** - These are file references for the game engine.

#### Hashtag Labels (`#*`)

Character identification tags for scripting system.

| Tag | Character | Purpose |
|-----|-----------|---------|
| `#ikut` | 郁人 | Ikuto character label |
| `#yuki` | 雪生? | Yuki character label |
| `#KANA` | - | System/character label |

**Usage:**
- Used in jump targets and labels
- Identifies which character route/scene
- Part of control flow system

**Do NOT translate** - These are system labels.

#### Effect References (`EFF\*`)

Visual effect animations used during scene transitions and dramatic moments.

| Effect Type | Japanese | Purpose |
|-------------|----------|---------|
| Flash | `EFF\フラッシュ２` | Screen flash effect |
| Directional wipe | `EFF\左〜右`, `EFF\右上〜左下` | Directional transitions |
| Blow effects | `EFF\ブロー（シャキーン）`, `EFF\ブロー中心` | Dramatic emphasis |
| Cylindrical | `EFF\円筒` | Circular/tunnel effects |
| Other effects | `EFF\ブロー５`, `EFF\ブロー左上` | Various transition effects |

**Full list found:**
```
EFF\フラッシュ₂           (Flash 2)
EFF\左〜右              (Left to right wipe)
EFF\ブロー（シャキーン）逆  (Blow/swoosh reverse)
EFF\右上〜左下            (Top-right to bottom-left)
EFF\ブロー（ぬるぽ）       (Blow/nurupo effect)
EFF\ブロー中心₂           (Center blow 2)
EFF\円筒                 (Cylinder/tunnel)
EFF\ブロー中心            (Center blow)
EFF\ブロー（シャキーン）縦  (Vertical blow)
EFF\ブロー（シャキーン）    (Standard blow)
EFF\ブロー５              (Blow 5)
EFF\ブロー左上            (Blow top-left)
```

**Also found:** `BG\black` - Background color (black screen transition)

**Do NOT translate** - These are engine effect file references.

#### Position/Animation Codes

| Format | Example | Purpose |
|--------|---------|---------|
| `・XXX` | `・060`, `・170` | Text position/animation ID |
| `・06X` | `・060`, `・062` | Position variants |

These codes control where text appears and how it's animated.

#### System Codes

| Code | Meaning |
|------|---------|
| `常：91` | Constant/system value 91 |
| `％名％` | Player name placeholder |
| `『Text』` | Email/text messages or quoted text |

### 4. Text Types in Scripts

#### Complete Text Type Breakdown

| Type | Pattern | Example | Translate? | Notes |
|------|---------|---------|------------|-------|
| **Dialogue** | `「Text」` | `「姉貴は寝てんだっつつの！」` | YES | Character speech (opcode 0x0B) |
| **Dialogue (cont.)** | `Text」` | `　だ、ごめん……」` | YES | Continuation, has 」 (opcode 0x0B) |
| **Inner Thought** | `＜Text＞` OR plain text | `＜うん、私も……たぶん＞` OR `そして、なんで目が覚めたんだろう？` | YES | Internal monologue (opcode 0x03/0x25) |
| **Email/Text Message** | `『Text』` | `『夕方はゴメン。具合、大丈夫か？』` | YES | In-game mail/message |
| **Quote/Written** | `『Text』` inside narration | `『透央が持ってきたやつ』って` | YES | Quote or text on object |
| **Narration** | Plain text | `何だかリビングの方がうるさい。` | YES | Description/inner thoughts |
| **Choices** | Plain text + next line has `選択パネル` | `砂糖を探し出して渡す` | YES | Player choice options |
| **Character Name** | Japanese name before dialogue (no length limit) | `郁人`, `ヒーローお兄さん`, `％名％` | NO | Speaker identifier |
| **Sound Effects** | `.wav` | `設備_部屋ドアOP.wav` | NO | Audio file reference |
| **Sprite Reference** | `ST_N\*` | `ST_N\ikuto_B_1_091` | NO | Character sprite file |
| **Hashtag Label** | `#*` | `#ikut`, `#KANA` | NO | Character/route identifier |
| **Effect Reference** | `EFF\*` | `EFF\フラッシュ₂` | NO | Visual effect file |
| **Background Reference** | `BG\*` | `BG\black` | NO | Background image |
| **Position Code** | `・XXX` | `・060` | NO | Text position/animation |
| **Name Placeholder** | `％名％` | Before dialogue → Character Name; inside dialogue → merge | SPECIAL | Player's name variable |
| **UI Marker** | UI text | `選択パネル` | NO | System UI element |
| **Season/Date Marker** | `名前：X` | `郁人：X`, `透央：X` | NO | Chapter/scene identifier |
| **System Code** | Technical | `常：91` | NO | Game state value |

#### How to Identify Text Types

**Dialogue:**
- Has `「` at start OR `」` at end
- Can be split across multiple lines
- If line 1 has `「`, line 2 might have continuation text
- If line ends with `」` (no opening), it's a continuation

**Inner Thought/Monologue:**
- Uses opcode 0x03 with sub-opcode 0x25
- Character's internal thoughts, not spoken aloud
- Can appear with OR without `＜＞` brackets
- With brackets: `＜大丈夫、よくなったよ＞` (direct inner thought)
- Without brackets: `そして、なんで目が覚めたんだろう？　とぼんやり思った。` (narration-style thought)

**Email/Text Messages:**
- Has `『` at start OR `』` at end (double brackets)
- Mail/message content from other characters
- Displayed on phone screens in-game
- Example: `『夕方はゴメン。具合、大丈夫か？』`
- Translation: YES - translate these

**Quotes/Written Text:**
- `『』` can also appear inside narration as quotes
- Or text written on objects (chocolate messages, etc.)
- Example: `『透央が持ってきたやつ』って、郁人が言った`

**Narration:**
- No brackets
- Longer descriptive text
- NOT followed by "選択パネル"

**Choices (Player Selection):**
- Plain text (no brackets)
- Followed by line containing "選択パネル"
- Multiple options appear in sequence

**Character Names (Speaker Labels):**
- Japanese text (any length) followed by dialogue starting with `「`
- Names: 郁人, 透央, 岬, etc.
- Names with titles: ヒーローお兄さん (8 chars), お姉さん, etc.
- Name Placeholder: `％名％` before dialogue becomes Character Name (speaker label)
- Do NOT translate - use romanization: Ikuto, Tomoomi, Misaki

**Name Placeholder (`％名％`) Rules:**
- BEFORE dialogue (`％名％「text」`) → Becomes **Character Name** (speaker label)
- INSIDE dialogue (`「text％名％more」`) → Merged into **Dialogue** text
- Detection: Checks if line has ANY Dialogue (not just immediate next entry)
- Binary pattern: `%<japanese name>` with NO closing `%` (character name marker)

#### Sentence Fragmentation

The game engine splits long sentences into multiple text strings for display pacing:

```
Original: 「ううん。今日は一日寝てたから、眠りが浅かったみたい」

In binary:
167. 「ううん。今日は一日寝てたから、
168. 　眠りが浅かったみたい」
```

**Binary Structure (Technical Detail):**

Within a single display unit (line), the game stores text segments as:
```
Segment 1: [text][0x00]  ← null-terminated
Delimiter: 0x09 (tab) + control codes (06 07 XX 07 for positioning)
Segment 2: [text][0x00]  ← null-terminated
```

Example from a_004 line 173:
```
Hex: 817582a082e882aa82c682a482b282b482a282dc82b7814282c582cd814182a282ab82dc82b582e582a4 00 09 02 0a 06 07 d9 07 00 00 03 25 00 2d 09 814082a98176 00
      「ありがとうございます。では、いきましょう                                                    null tab                              か」 null
```

**Key delimiters:**
- **0x00** (null) - terminates each text string
- **0x09** (tab) - main delimiter between text segments
- **06 07 XX 07** - positioning/control codes between segments

**Why it works this way:** The engine can display text with pauses, positioning changes, or effects between sentence fragments by storing them as separate null-terminated strings.

**When translating:** You may need to merge fragments or respect the split pattern.

### 5. Translation Guidelines

**DO Translate:**
- All dialogue: `「Text」` or continuation `Text」`
- Narration/description: Plain descriptive text
- Choices: Options followed by "選択パネル" marker
- Inner thoughts: Text in `『single brackets』`

**Do NOT Translate:**
- Sound effect filenames (`.wav`): Keep original Japanese
- Character names: 郁人, 透央, 岬 → Use romanization (Ikuto, Tomoomi, Misaki)
- Position codes: `・060`, `・170` etc.
- UI markers: `選択パネル`
- System codes: `常：91`
- Name placeholders: `％名％` (keep this exact format - engine replaces it)

**Special Handling:**
- **Sentence fragments** (like "やり思った。" + "てきた。"): These are split for pacing - translate each fragment naturally
- **Continuation dialogue** (starts with spaces + `」`): This is second part of split sentence, ensure it flows with previous part
- **Name placeholder `％名％`**: The game engine replaces this with player's name - keep format exactly

### 6. Character Routes

**Characters**: Chihiro (千尋), Ikuto (伊人), Tomoomi (朋臣), Yukio (雪生)

**File distribution**:
- Chihiro: `__c_001` - `__c_015` (15 files)
- Ikuto: `__i_001` - `__i_014` (14 files)
- Tomoomi: `__t_001` - `__t_011` (11 files)
- Yukio: `__y_001` - `__y_014` (14 files)

### 7. Ending Structure

```
__end_[character]_[type]
```

Types: `best`, `true`, `bad1-5`, `black`

Examples:
- `__end_c_best` - Chihiro best ending
- `__end_i_true` - Ikuto true ending
- `__end_t_bad1` - Tomoomi bad ending 1

### 8. Text Distribution

```
Total files: 1,264
Total texts: 84,839
Average: ~67 texts per file

Breakdown:
- Dialogue: ~70,000 (82%)
- Sound effects: ~1,500+ (.wav references)
- UI elements: ~10,000 (12%)
- System messages: ~4,000 (5%)
- Names: ~839 (1%)
```

---

## Text Extraction

### Process

```
Binary Script → SJIS Detection → Text Extraction → UTF-8 Output
```

### Algorithm

```python
# Scan for SJIS text start
if 0x81 <= byte <= 0x9F or 0xE0 <= byte <= 0xEF:
    text_start = offset
    # Find null terminator
    while offset < len(data) and data[offset] != 0x00:
        if is_sjis_start(data[offset]):
            offset += 2  # SJIS = 2 bytes
        else:
            offset += 1
    # Decode to UTF-8
    text = data[text_start:offset].decode('shift-jis')
    texts.append(text)
```

### Running

```bash
# Step 1: Extract text
python3 text_extractor.py [game_dir] [output_dir]

# Step 2: Validate extraction (IMPORTANT - run after any changes to text_extractor.py)
python3 audit_extraction.py
```

### Quality Assurance

The `audit_extraction.py` script validates extraction quality and catches common issues:

**What it checks:**
- Name Placeholders that are too long (>4 chars) or have punctuation
- Character Names that are too long (>12 chars) or have punctuation
- Short Narration entries on Dialogue lines (garbage detection)
- Name Placeholders on dialogue lines that weren't converted to Character Names

**Output example:**
```
Auditing 720 files...
✓ No issues found!
```

**If issues are found:**
```
Found 15 potential issues:

## Name Placeholder Has Punctuation: 8 occurrences
  eyes_y008.json:17
    Text: ％名％のことも、二人の関係も。
    Issue: Name Placeholder has punctuation (should be clean)
```

**When to run:**
- After any modifications to `text_extractor.py`
- Before committing changes to version control
- When investigating classification issues

---

## JSON Output Format

Each script file produces a corresponding JSON file with grouped text entries.

**File naming**: `<script_name>.json` (matches original binary filename)

**Structure**:
```json
{
  "lines": {
    "1": [
      {
        "type": "Narration",
        "original": "日常：105",
        "translation": null
      },
      {
        "type": "Background Reference",
        "original": "BG\\BG09_a"
      },
      {
        "type": "Sprite Reference",
        "original": "ST_L\\L_chihiro_A_1_081"
      }
    ],
    "2": [
      {
        "type": "Effect Reference",
        "original": "EFF\\左〜右"
      },
      {
        "type": "Hashtag Label",
        "original": "#chih"
      },
      {
        "type": "Character Name",
        "original": "千紘"
      },
      {
        "type": "Dialogue",
        "original": "「この後、実行委員会の集まりがあるから、３",
        "translation": null
      },
      {
        "type": "Dialogue",
        "original": "　人は俺の話が終わったらすぐ１階のＡクラス",
        "translation": null
      },
      {
        "type": "Dialogue",
        "original": "　に行くように」",
        "translation": null
      }
    ]
  },
  "metadata": {
    "file": "a_014k",
    "total_lines": 173,
    "translatable": 4
  }
}
```

**Field descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `lines` | Object | Keys are line numbers (as strings), values are arrays of text entries |
| `type` | String | Text type (Dialogue, Narration, Sound Effect, etc.) - see Text Types section |
| `original` | String | Original Japanese text |
| `translation` | String/null | Translation field (only present for translatable entries, initially `null`) |
| `metadata.file` | String | Source script filename |
| `metadata.total_lines` | Number | Total line count in script |
| `metadata.translatable` | Number | Count of entries that should be translated |

**Text types with `translation` field**: Dialogue, Narration, Inner Thought, Email/Text Message

**Text types WITHOUT `translation` field**: Sound Effect, Sprite Reference, Hashtag Label, Effect Reference, Background Reference, Position Code, Character Name, Season/Date Marker, UI Marker, System Code

---

## Script Recompilation

### Process

```
Original + Translated UTF-8 → Text Replacement → Shift-JIS → Binary
```

### Algorithm

```python
# Find all text positions in original
texts = find_text_strings(original_data)

# Read translated text
translations = read_translated_file(translated_file)

# Replace each text
for i, (offset, original_bytes) in enumerate(texts):
    translated = translations[i]
    new_bytes = translated.encode('shift-jis')

    if len(new_bytes) <= len(original_bytes):
        # Replace in-place, pad with nulls
        data[offset:offset+len(new_bytes)] = new_bytes
        # Fill remaining with null bytes
    else:
        # Truncate (or use smart compiler)
        new_bytes = new_bytes[:len(original_bytes)]
```

### Running

```bash
# Compiler (simple string replacement)
python3 compiler_smart.py
```

---

## Text Length Solutions

### The Problem

Japanese characters are often shorter in bytes than English:

```
Japanese: 先生には頼らない
- 10 characters × 2 bytes = 20 bytes (SJIS)

English: I won't rely on the teacher
- 27 characters × 1 byte = 27 bytes (ASCII)
```

### The Solution

The compiler performs simple byte replacement:
- Writes English text at the same offset as Japanese text
- File size may increase if translations are longer

### Example Compilation

```
Input file __c_001_text.txt:
1. そう、ですよね……
2. 先生には頼らない
...

Output:
✓ Line 1: "Yes, that's right..." (18 → 20 bytes)
✓ Line 2: "I won't rely on the teacher" (16 → 27 bytes, file expands)
```

**Note**: The game engine may have issues with modified file sizes/offsets.

---

## Sample Input/Output

### Example 1: Text Replacement

**Original Binary**:
```
82bb82a4814182c582b782e682cb81638163  (SJIS)
= "そう、ですよね……" (18 bytes)
```

**Extracted Text**:
```
1. そう、ですよね……
```

**Translated**:
```
1. Yes, that's right...
```

**Compiled Binary**:
```
5965732c207468617427732072696768742e2e  (SJIS/ASCII)
= "Yes, that's right..." (22 bytes)
```

### Example 2: Long Text Handling

**Original**:
```
先生には頼らない (16 bytes at offset 1000)
```

**Translation** (27 bytes):
```
I won't rely on the teacher
```

**Compiler Output**:
```
I won't rely on the teacher (27 bytes written at offset 1000)
```

**Note**: File size increases by 11 bytes. Subsequent data is shifted forward.

---

## Binary Structure Analysis

### Byte Distribution

From analysis of `a_013a` (14,208 bytes):

| Byte Range | Count | Purpose |
|------------|-------|---------|
| 0x00 | 1564 | Null terminators, padding |
| 0x81 | 789 | SJIS first byte (CJK range) |
| 0x82 | 2291 | SJIS first byte (most common text) |
| 0x83 | 263 | SJIS first byte (half-width katakana range) |
| 0x03, 0x08, 0x0A, 0x0B | 100+ | Opcodes |
| 0x09 | 272 | Text markers |
| 0x40-0x5F | 500+ | Parameters, addresses |

### Detailed Instruction Breakdown

**Example from a_013a (offset 0x00):**
```
0000: 0b 26 93 fa 8f ed 81 46 39 31 00 05 4d 2d 08 00 12 47
      └─┬─┘└──────┴──────┴──────┴───┴───┴─┴───────┴───┴───┴───┴───┐
       │    Parameters           │  │   │              │         │
       Text Display              │  │   │              │         │
                                  │  │   │              │         │
       Position data ─────────────┘  │   │              │         │
                                     │   │              │         │
       Register/Value ────────────────┘   │              │         │
                                         │              │         │
       Register Set opcode ───────────────┘              │         │
                                                        │         │
       Variable reference ────────────────────────────────┘         │
                                                                  │
       Next instruction starts ────────────────────────────────────┘
```

**Text Display Sequence (offset 0x30):**
```
0030: 03 25 00 2d 09 82 bb 82 b5 82 c4 81 41 82 c8 82 f1 82 c5
      │  │  │  │  │  └───────────────────────────────────────────┐
      │  │  │  │  │     SJIS text: "そして、なんで目が覚めた"     │
      │  │  │  │  │     (And, why did I wake up)                │
      │  │  │  │  │                                            │
      │  │  │  │  └─ Text starts here                           │
      │  │  │  │                                               │
      │  │  │  └─ Marker (0x09)                                │
      │  │  │                                                  │
      │  │  └─ Parameter (0x2d = 45)                          │
      │  │                                                     │
      │  └─ Sub-opcode (0x00)                                 │
      │                                                        │
      └─ Command opcode (0x03)                                 │
                                                             │
0040: 96 da 82 aa 8a 6f 82 df 82 bd 82 f1 82 be 82 eb 82 a4 81 48
      └───────────────────────────────────────────────────────┘
      SJIS text continues: "んだろう？とぼんやり思った。"
```

**Label Definition (offset 0xB0):**
```
00b0: 0a 16 23 69 6b 75 74 01 00 01 00 00 00 00 00 4f 60 00
      │  └─┬─┘└──────┘└───────────────────────────────────────┐
      │     │      │                                          │
      │     │      └─ Label name: "#ikut"                     │
      │     │                                                 │
      │     └─ Length (0x16 = 22 bytes including #)           │
      │                                                       │
      └─ Label opcode (0x0A)                                  │
                                                            │
00c0: 00 6e 73 f7 05 08 25 88 e8 90 6c 00 00 06 07 82 18 00
      └─ Next instruction (register operation) ─────────────┘
```

### Data Types in Binary

**SJIS Text Encoding:**
- **Double-byte characters**: 0x81-0x9F, 0xE0-0xEF (first byte)
- **ASCII**: 0x20-0x7E
- **Half-width katakana**: 0xA1-0xDF
- **Null terminator**: 0x00

**Common Byte Values:**
```
0x00: 1564 times - Null terminator
0x01: 128 times - Boolean true
0x02: 169 times - Boolean false
0x03: 102 times - Command opcode
0x09: 272 times - Text marker
0x0A: 169 times - Label opcode
0x81: 789 times - SJIS first byte
0x82: 2291 times - SJIS first byte (hiragana/katakana)
0x83: 263 times - SJIS first byte (kanji range)
```

---

## Opcode Reference

### Common Opcodes

| Opcode | Name | Format | Purpose |
|--------|------|--------|---------|
| 0x00 | Null Terminator | `00` | End of string/data |
| 0x03 | Command | `03 2E <type> <params>` | Engine command |
| 0x08 | Register Set | `08 52 3d <name> <value>` | Initialize variable |
| 0x09 | Text Marker | `09 <text>` | Text boundary marker |
| 0x0A | Label | `0A 21 21 40 <name> 00` | Define jump target |
| 0x0B | Text Display | `0B <type> <params> <text> 00` | Show text |
| 0x0D | Function Call | `0D <count> <name> 00` | Call function |
| 0x0E | Goto | `0E <label> 00` | Jump to label |
| 0x40 | Jump Target | `40 <label> 00` | Target reference |
| 0x41 | Expression | `41 <params>` | Variable operation |
| 0x42 | Condition | `42 <params>` | Conditional jump |
| 0x5F | Control | `5F <params>` | Flow control |
| 0x7E | Parameter | `7E <value>` | Parameter value |

### Command Types (0x03 sub-opcodes)

| Sub-Op | Name | Purpose |
|--------|------|---------|
| 0x04 | Variable check | Test variable value |
| 0x05 | Flag check | Test flag state |
| 0x09 | Text parameter | Text data parameter |
| 0x0B | Compare | Compare values |
| 0x0D | Wait | Wait for click/input |
| 0x25 | Inner Thought | Display monologue (text uses `＜＞` brackets) |
| 0x2D | Text parameter | Text data parameter |
| 0x2E | Expression | Evaluate expression |

**Inner Thought Command (0x25):**
```
03 25 00 2d 09 <text> 00
│  │  │  │  │
│  │  │  │  └─ Text marker
│  │  │  └─ Parameter (0x2d)
│  │  └─ Separator (0x00)
│  └─ Sub-opcode: Inner Thought
└─ Command opcode

Text format: ＜monologue text＞
Example: ＜うん、私も……たぶん、明日には学園行けると思う＞
```

This command displays character's internal thoughts/monologue, distinguished from regular dialogue (0x0B) by using `＜＞` brackets instead of `「」`.

### Variable Operations (0x08)

The game uses a variable system for tracking state:
- **Flags**: Boolean values (true/false) for story choices
- **Counters**: Numeric values (affection, events seen, etc.)
- **Strings**: Character names, labels, file references

**Variable names found:**
- `f.` - Flags (f.df, f.bg, etc.)
- `BG` - Background references (BG\BG01_c)
- Memory labels (Memory01-25)

### Control Flow

**Labels:**
- Format: `@label_name` or `!!@label_name`
- Character routes: `@c_001`, `@i_001`, `@t_001`, `@y_001`
- Common events: `@a_001` (all routes)
- Endings: `@end_c_best`, `@end_i_true`, etc.

**Conditional Jumps:**
```
03 2E 04 <param>     - Check variable
0E <label> 00        - Jump if condition met
```

**Function Calls:**
```
0D <count> <function_name> 00
Example: Call function with parameter count
```

### Game State Structure

**File-Based State:**
- `Memory01` - `Memory25`: Save/restore points
- `FlgTbl`: Flag table (global game state)
- `LoveComparison`: Affection values for characters
- `Key*`: Route unlock keys (KeyChihiro, KeyIkuto, etc.)
- `Dream`: Dream event state
- `CheckValue*`: Character-specific values

**Variables by Type:**

| Type | Purpose | Examples |
|------|---------|----------|
| Route flags | Which character route | `df`, `ikuto`, `chihiro` |
| Event flags | Events seen | `ev001`, `ev002` |
| Choice flags | Player choices | `sel001`, `sel002` |
| affection | Character affection | `love_c`, `love_i` |
| Background | Current BG | `BG\BG01_c` |
| Position | Text position | `pos_x`, `pos_y` |

### Text Instruction Detail

```
0B 24/2E [15-16 bytes] [Shift-JIS text] 00
│  │      │              │              │
│  │      │              │              └─ Null terminator
│  │      │              └─ Text string
│  │      └─ Parameters (offset, color, etc.)
│  └─ Display type (standard/special)
└─ Text display opcode
```

### Wait Command

```
03 2E 0D 91 49 91 F0
│  │  │  └───┴───┴─ Timing value
│  │  └─ Wait for click
│  └─ Expression
└─ Command
```

---

## Troubleshooting

### Text Not Extracting

**Problem**: Empty extracted text files

**Solutions**:
1. Verify file is binary: `file __c_001` (should say "data")
2. Check for SJIS text: `xxd __c_001 | grep "8[123456789a-f]"`
3. Ensure file is not corrupted

### Text Too Long

**Problem**: Warning about text length

**Solutions**:
1. Use `compiler_smart.py` for auto-shortening
2. Manually abbreviate: "don't", "I'm", "cannot"
3. Remove unnecessary words: "Please" → "Plz"
4. Use shorter alternatives

### Encoding Errors

**Problem**: `UnicodeEncodeError`

**Causes**: Special characters not in SJIS

**Characters to avoid**:
- Emoji: 😊 😂 ❤️
- Symbols: © ® ™
- Quotes: " " " " (use regular quotes)

**Solution**: Replace with ASCII equivalents

### Game Crashes

**Possible causes**:
1. Text truncated mid-SJIS character
2. File size mismatch
3. Corrupted encoding

**Debug**:
```bash
# Compare sizes
ls -l original/__c_001 compiled/__c_001

# Check encoding
xxd compiled/__c_001 | grep "82"
```

### Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `list index out of range` | Mismatched line numbers | Check translation file numbering |
| `UnicodeEncodeError` | Invalid characters | Remove emoji/symbols |
| `FileNotFoundError` | Wrong file name | Check naming convention |

---

## File Reference

### Character Encoding Table

| Char | SJIS Bytes | Unicode |
|------|------------|---------|
| あ | 82 A0 | U+3042 |
| 漢 | 8A 6F | U+6F22 |
| 。 | 81 42 | U+3002 |
| 、 | 81 41 | U+3001 |
| 「 | 81 45 | U+300C |
| 」 | 81 46 | U+300D |

### Quick Reference

```
EXTRACT:
  python3 text_extractor.py [game_dir] [output_dir]
  Output: JSON files in extracted_texts/

TRANSLATE:
  Edit extracted_texts/*_text.json
  - Add "translation" field to translatable entries
  - Keep UTF-8 encoding
  - Preserve JSON structure

COMPILE:
  python3 compiler.py      (basic)
  python3 compiler_smart.py (with shortening)

TEST:
  1. Backup originals!
  2. Test single file
  3. Check game runs
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2024-01-01 | Initial LittleCheese decompiler |
| 1.1 | 2024-01-01 | Added smart compiler with auto-shortening |

## Support

For issues:
1. Check Troubleshooting section
2. Verify file encodings (UTF-8 for translations)
3. Test with single files first
