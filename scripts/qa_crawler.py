import os
import sys
import traceback
from app import app, db
from models import User

def main():
    # Setup test client
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    
    # We may need a dummy user for login_required routes
    # But for a quick crawl, we can just see what throws a 500 error vs a 401/403/302
    
    client = app.test_client()
    
    issues = []
    
    with app.app_context():
        # Iterate all routes
        for rule in app.url_map.iter_rules():
            # Skip static
            if rule.endpoint == 'static':
                continue
                
            methods = rule.methods - {'OPTIONS', 'HEAD'}
            if not methods:
                continue
                
            method = 'GET' if 'GET' in methods else list(methods)[0]
            
            # Construct dummy URL
            # replace <int:id> with 1, <slug> with 'test', etc
            url = rule.rule
            import re
            url = re.sub(r'<int:[^>]+>', '1', url)
            url = re.sub(r'<[^>]+>', 'test', url)
            
            try:
                if method == 'GET':
                    response = client.get(url)
                else:
                    response = client.post(url, data={})
                
                # We expect 200, 302 (redirect), 401 (unauth), 403 (forbidden), 404 (if our dummy param fails)
                # 500 means an actual server error (template error, etc)
                if response.status_code == 500:
                    issues.append(f"[500] {method} {url} (Endpoint: {rule.endpoint})")
            except Exception as e:
                issues.append(f"[EXCEPTION] {method} {url} - {str(e)}")
                
    print("--- Crawler Issues ---")
    for issue in issues:
        print(issue)
    if not issues:
        print("No 500s or exceptions found during basic crawl.")

if __name__ == '__main__':
    main()
