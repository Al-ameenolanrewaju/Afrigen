import os
import re
from app import app

def main():
    with app.app_context():
        # Get all registered endpoints in main blueprint
        all_endpoints = {rule.endpoint for rule in app.url_map.iter_rules() if rule.endpoint.startswith('main.')}
        
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
                        
    # Endpoints that are registered but never called via url_for in templates
    unused_endpoints = all_endpoints - found_endpoints
    print("Potentially Unused Endpoints:")
    for ep in sorted(unused_endpoints):
        print(f" - {ep}")

if __name__ == '__main__':
    main()
