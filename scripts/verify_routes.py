import os
import re
from app import app

def main():
    with app.app_context():
        valid_endpoints = set(rule.endpoint for rule in app.url_map.iter_rules())
        
    template_dir = 'templates'
    url_for_pattern = re.compile(r"url_for\(\s*['\"]([^'\"]+)['\"]")
    
    found_endpoints = set()
    for root, dirs, files in os.walk(template_dir):
        for file in files:
            if file.endswith('.html'):
                filepath = os.path.join(root, file)
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    matches = url_for_pattern.findall(content)
                    for match in matches:
                        found_endpoints.add(match)
                        
    invalid_endpoints = found_endpoints - valid_endpoints
    print("Invalid Endpoints:")
    for ep in invalid_endpoints:
        print(f" - {ep}")

if __name__ == '__main__':
    main()
