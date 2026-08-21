import os
import re

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Add timezone to import if not present
    if 'from datetime import ' in content and 'timezone' not in content:
        content = re.sub(r'(from datetime import [^\n]+)', r'\1, timezone', content, count=1)
    elif 'import datetime' in content and 'timezone' not in content:
        # Actually it's easier to just append 'from datetime import timezone' after the imports
        # But we'll just handle it by regex replacing datetime.utcnow()
        pass

    # Replace datetime.utcnow()
    content = content.replace('datetime.utcnow()', 'datetime.now(timezone.utc)')
    content = content.replace('datetime.datetime.utcnow()', 'datetime.datetime.now(datetime.timezone.utc)')

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Fixed {filepath}")

def main():
    files = [
        r'c:\Users\ADEDAMOLA\Desktop\afrigen\content_engine\planner.py',
        r'c:\Users\ADEDAMOLA\Desktop\afrigen\services\blog.py',
        r'c:\Users\ADEDAMOLA\Desktop\afrigen\services\automation.py',
        r'c:\Users\ADEDAMOLA\Desktop\afrigen\services\newsletter.py'
    ]
    for f in files:
        fix_file(f)

if __name__ == '__main__':
    main()
