# -*- coding: utf-8 -*-
"""Fix remaining 4 corrupted spots in feishu_service.py"""

with open('app/services/feishu_service.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix remaining corrupted replacement characters
text = text.replace('\ufffd,\r\n', '。",\r\n')
text = text.replace('f"**\ufffd\u539f\u59cb\u63d0\u793a\ufffd*', 'f"**\u2728 \u539f\u59cb\u63d0\u793a\u8bcd**')
text = text.replace('f"**\ufffd\u4f18\u5316\u7ed3\u679c**', 'f"**\u2728 \u4f18\u5316\u7ed3\u679c**')

remaining = text.count('\ufffd')
print(f'Remaining replacement chars: {remaining}')

if remaining > 0:
    import re
    for m in re.finditer('\ufffd', text):
        s = m.start()
        ctx = text[max(0,s-15):s+15]
        print(f'  At pos {s}: ...{repr(ctx)}...')

with open('app/services/feishu_service.py', 'w', encoding='utf-8', newline='\r\n') as f:
    f.write(text)

print('Done!')
