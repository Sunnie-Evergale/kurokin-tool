#!/usr/bin/env python3
"""
Audit extracted text files for potential classification issues.
Run this after text_extractor.py to validate results.
"""

import json
import os
import sys
from pathlib import Path

def check_file(filepath):
    """Check a single JSON file for issues"""
    issues = []
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)

    for line_num, entries in data.get('lines', {}).items():
        for i, entry in enumerate(entries):
            text_type = entry.get('type')
            original = entry.get('original', '')

            # Rule 1: Name Placeholder should be short and clean
            if text_type == "Name Placeholder":
                if len(original) > 4:
                    issues.append({
                        'file': filepath.name,
                        'line': line_num,
                        'type': 'Name Placeholder Too Long',
                        'text': original,
                        'issue': f'Name Placeholder is {len(original)} chars (should be ≤4)'
                    })
                if any(c in original for c in '！？、。！？」」』』―'):
                    issues.append({
                        'file': filepath.name,
                        'line': line_num,
                        'type': 'Name Placeholder Has Punctuation',
                        'text': original,
                        'issue': 'Name Placeholder has punctuation (should be clean)'
                    })

            # Rule 2: Character Name should be short and clean
            if text_type == "Character Name":
                if len(original) > 12:
                    issues.append({
                        'file': filepath.name,
                        'line': line_num,
                        'type': 'Character Name Too Long',
                        'text': original,
                        'issue': f'Character Name is {len(original)} chars (should be ≤12)'
                    })
                if any(c in original for c in '！？、。！？」」』』―'):
                    issues.append({
                        'file': filepath.name,
                        'line': line_num,
                        'type': 'Character Name Has Punctuation',
                        'text': original,
                        'issue': 'Character Name has punctuation (should be clean)'
                    })

            # Rule 3: Narration on same line as Dialogue (potential split dialogue)
            if text_type == "Narration" and len(original) <= 2:
                line_has_dialogue = any(e.get('type') == "Dialogue" for e in entries)
                if line_has_dialogue:
                    issues.append({
                        'file': filepath.name,
                        'line': line_num,
                        'type': 'Short Narration on Dialogue Line',
                        'text': original,
                        'issue': 'Very short narration on line with dialogue (garbage?)'
                    })

            # Rule 4: Name Placeholder alone on a line with dialogue (should be Character Name)
            if text_type == "Name Placeholder" and len(original) <= 4:
                line_has_dialogue = any(
                    e.get('type') == "Dialogue" and e.get('original', '').startswith('「')
                    for e in entries
                )
                if line_has_dialogue and not any(c in original for c in '！？、。！？」」』』―'):
                    issues.append({
                        'file': filepath.name,
                        'line': line_num,
                        'type': 'Name Placeholder Not Converted',
                        'text': original,
                        'issue': 'Clean Name Placeholder on dialogue line (should be Character Name?)'
                    })

    return issues

def main():
    extracted_dir = Path("extracted_texts")

    if not extracted_dir.exists():
        print(f"Error: {extracted_dir} directory not found")
        sys.exit(1)

    all_issues = []
    json_files = list(extracted_dir.glob("*.json"))

    print(f"Auditing {len(json_files)} files...")
    print()

    for filepath in sorted(json_files):
        issues = check_file(filepath)
        all_issues.extend(issues)

    # Group issues by type
    issues_by_type = {}
    for issue in all_issues:
        issue_type = issue['type']
        if issue_type not in issues_by_type:
            issues_by_type[issue_type] = []
        issues_by_type[issue_type].append(issue)

    # Report results
    if all_issues:
        print(f"Found {len(all_issues)} potential issues:\n")

        for issue_type, issues in sorted(issues_by_type.items()):
            print(f"## {issue_type}: {len(issues)} occurrences")
            for issue in issues[:5]:  # Show first 5 of each type
                print(f"  {issue['file']}:{issue['line']}")
                print(f"    Text: {issue['text'][:50]}...")
                print(f"    Issue: {issue['issue']}")
            if len(issues) > 5:
                print(f"  ... and {len(issues) - 5} more")
            print()

        print(f"Total: {len(all_issues)} issues across {len(json_files)} files")
        return 1
    else:
        print("✓ No issues found!")
        return 0

if __name__ == "__main__":
    sys.exit(main())
