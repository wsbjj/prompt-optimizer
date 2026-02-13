# -*- coding: utf-8 -*-
"""Clean feishu_service.py - remove excessive blank lines"""

with open('app/services/feishu_service.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove lines that are just whitespace or have only spaces
cleaned_lines = []
prev_blank = False
for line in lines:
    # Check if line is blank (only whitespace)
    is_blank = line.strip() == ''
    
    # Only add blank line if previous wasn't blank (max 1 consecutive blank)
    if is_blank:
        if not prev_blank:
            cleaned_lines.append('\n')
        prev_blank = True
    else:
        cleaned_lines.append(line)
        prev_blank = False

# Write back
with open('app/services/feishu_service.py', 'w', encoding='utf-8') as f:
    f.writelines(cleaned_lines)

print(f'Cleaned! Reduced from {len(lines)} to {len(cleaned_lines)} lines')
