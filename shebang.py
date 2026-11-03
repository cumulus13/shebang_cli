#!/usr/bin/env python3

# File: shebang_cli/shebang.py
# Author: Hadi Cahyadi <cumulus13@gmail.com>
# Date: 2026-11-03
# Description: Scan files and safely inject/update license headers (Supports Web & Block Comments).
# License: MIT

import sys
import argparse
import glob
import re
from datetime import datetime
from pathlib import Path

from rich.console import Console

# Initialize Rich console
console = Console()

DEFAULT_AUTHOR = "Hadi Cahyadi <cumulus13@gmail.com>"
DEFAULT_LICENSE = "MIT"

# === RICH TAG CONFIGURATION ===
TAG_SKIPPED = "[black on #FFFF00][SKIPPED][/]"
TAG_DRY_RUN = "[bold #AAAAFF][DRY-RUN][/]"
TAG_UPDATED = "[black on #00FFFF][UPDATED][/]"
TAG_ERROR   = "[white on #FF0000][ERROR][/]"
TAG_SKIP    = "[white on #808080][SKIP][/]"
# ===============================

def get_comment_style(file_path: Path) -> dict:
    """Returns the comment styling based on the file extension."""
    ext = file_path.suffix.lower()
    
    # 1. Block comment styles (Web files)
    if ext in [".html", ".htm", ".xml", ".svg", ".vue", ".svelte"]:
        return {"prefix": "", "start": "<!--", "end": "-->"}
    if ext in [".css", ".scss", ".sass", ".less"]:
        return {"prefix": " *", "start": "/*", "end": "*/"}

    # 2. Single-line comment styles
    single_line_styles = {
        ".py": "#", ".sh": "#", ".bash": "#", ".toml": "#", ".yaml": "#", ".yml": "#",
        ".rb": "#", ".pl": "#",
        ".js": "//", ".ts": "//", ".java": "//", ".c": "//", ".cpp": "//", ".cc": "//", ".cs": "//",
        ".go": "//", ".rs": "//", ".dart": "//", ".php": "//",
        ".bat": "::", ".cmd": "::",
        ".lua": "--", ".sql": "--",
        ".hs": "--"
    }
    
    # Fallback to standard C-style // if unknown
    return {"prefix": single_line_styles.get(ext, "//"), "start": None, "end": None}


def find_project_root(start_path: Path) -> Path:
    """Smartly find the project root by looking for common markers."""
    current = start_path.resolve()
    if current.is_file():
        current = current.parent
        
    for _ in range(10):  # Limit depth to prevent infinite loops
        if any((current / marker).exists() for marker in [".git", "pyproject.toml", "package.json"]):
            return current.parent 
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None

def strip_existing_header(content: str, style: dict) -> tuple[str, str, str, str]:
    """
    Safely strips old headers (both single-line and block comments)
    while extracting existing Date and Description.
    """
    lines = content.splitlines(keepends=True)
    if not lines:
        return "", "", "", ""

    prefix = style.get("prefix", "")
    b_start = style.get("start")
    b_end = style.get("end")

    shebang = ""
    idx = 0
    
    # 1. Preserve existing shebang (typically for Python/Bash, won't affect HTML/CSS)
    if lines[idx].startswith("#!"):
        shebang = lines[idx].strip()
        idx += 1

    # Skip empty lines immediately after shebang
    while idx < len(lines) and lines[idx].strip() == "":
        idx += 1

    if idx >= len(lines):
        return shebang, "", "", "".join(lines[idx:])

    existing_date = ""
    existing_desc = ""
    header_keywords = ["author:", "file:", "full path:", "date:", "license:", "description:"]
    end_of_header = idx

    # === BLOCK COMMENT HANDLING (HTML, CSS) ===
    if b_start:
        if lines[idx].strip().startswith(b_start):
            in_header_block = False
            temp_end = idx
            
            # First pass: check if this block is actually our license header
            for i in range(idx, len(lines)):
                if any(kw in lines[i].lower() for kw in header_keywords):
                    in_header_block = True
                if b_end in lines[i]:
                    temp_end = i
                    break
            
            if in_header_block:
                # Extract fields before stripping
                for i in range(idx, temp_end + 1):
                    line_stripped = lines[i].strip()
                    
                    date_match = re.search(r'date:\s*(.*)', line_stripped, re.IGNORECASE)
                    if date_match:
                        d = date_match.group(1).strip()
                        if d.endswith(b_end): d = d[:-len(b_end)].strip()
                        existing_date = d
                        
                    desc_match = re.search(r'description:\s*(.*)', line_stripped, re.IGNORECASE)
                    if desc_match:
                        d = desc_match.group(1).strip()
                        if d.endswith(b_end): d = d[:-len(b_end)].strip()
                        existing_desc = d
                
                end_of_header = temp_end + 1
        
    # === SINGLE-LINE COMMENT HANDLING ===
    else:
        for i in range(idx, len(lines)):
            line = lines[i]
            line_stripped = line.strip()

            if line_stripped == "":
                end_of_header = i + 1
                continue

            # Stop entirely if we hit code or a different comment style
            if not line_stripped.startswith(prefix):
                break

            line_lower = line_stripped.lower()
            
            # Check if this specific comment line is part of our generated header
            is_header_field = any(kw in line_lower for kw in header_keywords)
            is_empty_comment = line_stripped == prefix or line_stripped == prefix.strip()

            if is_header_field or is_empty_comment:
                end_of_header = i + 1
                
                # Extract preserving fields
                date_match = re.search(r'date:\s*(.*)', line_stripped, re.IGNORECASE)
                if date_match:
                    existing_date = date_match.group(1).strip()
                    
                desc_match = re.search(r'description:\s*(.*)', line_stripped, re.IGNORECASE)
                if desc_match:
                    existing_desc = desc_match.group(1).strip()
            else:
                # Reached a REAL user comment. DO NOT STRIP!
                break

    # Strip trailing empty lines left behind by the header removal
    while end_of_header < len(lines) and lines[end_of_header].strip() == "":
        end_of_header += 1

    return shebang, existing_date, existing_desc, "".join(lines[end_of_header:])

def generate_header(style: dict, author: str, date_str: str, license_name: str, desc_str: str, rel_path: str = None, full_path: str = None) -> str:
    prefix = style.get("prefix", "")
    b_start = style.get("start")
    b_end = style.get("end")

    lines = []
    
    if b_start:
        lines.append(b_start)

    def fmt(text):
        return f"{prefix} {text}".rstrip() if prefix else text

    if rel_path:
        lines.append(fmt(f"File: {rel_path.replace(chr(92), '/')}"))
    if full_path:
        lines.append(fmt(f"Full Path: {full_path}"))
        
    lines.append(fmt(f"Author: {author}"))
    lines.append(fmt(f"Date: {date_str}"))
    lines.append(fmt(f"Description: {desc_str}"))
    lines.append(fmt(f"License: {license_name}"))
    
    if b_end:
        lines.append(b_end)
        
    return "\n".join(lines) + "\n\n"

def resolve_target_files(target: str, ext_filter: str = None):
    path_obj = Path(target)
    files = []
    root_folder = None

    if path_obj.is_dir():
        root_folder = path_obj
        pattern = f"**/*{ext_filter}" if ext_filter else "**/*"
        files = [p for p in path_obj.glob(pattern) if p.is_file()]
    elif "*" in target or "?" in target:
        base_dir_str = target.split("*")[0].split("?")[0]
        if base_dir_str and Path(base_dir_str).exists():
            root_folder = Path(base_dir_str)
            if root_folder.is_file():
                root_folder = root_folder.parent

        # Fix: Dynamically make ANY extension wildcard recursive
        if "**" not in target:
            if target.startswith("*."):
                target = "**/" + target
            else:
                target = target.replace("/*.", "/**/*.").replace("\\*.", "\\**\\*.")

        matched = glob.glob(target, recursive=True)
        files = [Path(f) for f in matched if Path(f).is_file()]
    elif path_obj.is_file():
        root_folder = path_obj.parent
        files = [path_obj]

    if root_folder and root_folder.name:
        root_folder = root_folder.parent

    return sorted(list(set(files))), root_folder

def process_file(file_path: Path, fallback_root: Path, path_type: str, dry_run: bool, author: str, license_name: str):
    style = get_comment_style(file_path)
    full_path_str = str(file_path.resolve())

    smart_root = find_project_root(file_path) or fallback_root
    
    if smart_root:
        try:
            rel_path_str = str(file_path.resolve().relative_to(smart_root.resolve()))
        except ValueError:
            rel_path_str = file_path.name
    else:
        rel_path_str = file_path.name

    rel_p = rel_path_str if path_type in ["relative", "both"] else None
    full_p = full_path_str if path_type in ["full", "both"] else None

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except UnicodeDecodeError:
        console.print(f"{TAG_SKIP} Encoding error, not a UTF-8 text file: {file_path}")
        return
    except Exception as e:
        console.print(f"{TAG_ERROR} Could not read {file_path}: {e}")
        return

    # Strip old header and retrieve existing values to prevent unnecessary updates
    shebang, existing_date, existing_desc, cleaned_content = strip_existing_header(content, style)
    
    # Use existing date if found, otherwise generate a new one
    date_str = existing_date if existing_date else datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    
    new_header = generate_header(style, author, date_str, license_name, existing_desc, rel_path=rel_p, full_path=full_p)
    
    # Reassemble: Original Shebang -> New Header -> Original Content
    final_content = ""
    if shebang:
        final_content += shebang + "\n\n"
    final_content += new_header + cleaned_content

    # EXACT MATCH CHECK: If nothing has functionally changed, do not touch the file
    if final_content == content:
        console.print(f"{TAG_SKIPPED} {file_path} [white on blue](Already up to date)[/]")
        return

    if dry_run:
        console.print(f"{TAG_DRY_RUN} [bold #FF5500]Would update:[/] [bold #00FFFF]{file_path}[/]")
    else:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(final_content)
        console.print(f"{TAG_UPDATED} {file_path}")

def main():
    try:
        from rchf import CustomRichHelpFormatter
    except:
        CustomRichHelpFormatter = argparse.RawTextHelpFormatter
    parser = argparse.ArgumentParser(description="Scan files and safely inject/update license headers.", prog='shebang', formatter_class=CustomRichHelpFormatter)
    
    parser.add_argument("target", help="Directory path or pattern (e.g., 'c:\\PROJECTS\\pyproject-forge\\*.py')")
    parser.add_argument(
        "-b",
        "--path-type",
        choices=["relative", "full", "both"],
        default="relative",
        help="Path inclusion type (default: relative)",
    )
    parser.add_argument(
        "-l",
        "--license",
        default=DEFAULT_LICENSE,
        help=f"License name to inject (default: {DEFAULT_LICENSE})"
    )
    parser.add_argument(
        "-a",
        "--author",
        default=DEFAULT_AUTHOR,
        help=f"Author string to inject (default: '{DEFAULT_AUTHOR}')"
    )
    parser.add_argument(
        "-t",
        "--dry-run",
        action="store_true",
        help="Simulate execution without modifying files",
    )

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit()

    args = parser.parse_args()
    matched_files, fallback_root = resolve_target_files(args.target)

    if not matched_files:
        console.print("[yellow]No files matched target.[/]")
        return

    for path in matched_files:
        process_file(path, fallback_root, args.path_type, args.dry_run, args.author, args.license)

if __name__ == "__main__":
    main()