import os
import hashlib
from collections import defaultdict

def get_file_hash(filepath):
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        buf = f.read()
        hasher.update(buf)
    return hasher.hexdigest()

def find_duplicates(directory, extensions):
    hashes = defaultdict(list)
    for root, dirs, files in os.walk(directory):
        for file in files:
            if any(file.endswith(ext) for ext in extensions):
                filepath = os.path.join(root, file)
                file_hash = get_file_hash(filepath)
                hashes[file_hash].append(filepath)
    
    duplicates = {k: v for k, v in hashes.items() if len(v) > 1}
    return duplicates

def main():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(base_dir, 'static')
    templates_dir = os.path.join(base_dir, 'templates')

    print("--- Duplicate CSS/JS in static/ ---")
    static_dupes = find_duplicates(static_dir, ['.css', '.js'])
    for h, paths in static_dupes.items():
        print(f"Hash {h[:8]}:")
        for p in paths:
            print(f"  {os.path.relpath(p, base_dir)}")

    print("\n--- Duplicate Templates in templates/ ---")
    template_dupes = find_duplicates(templates_dir, ['.html'])
    for h, paths in template_dupes.items():
        print(f"Hash {h[:8]}:")
        for p in paths:
            print(f"  {os.path.relpath(p, base_dir)}")

if __name__ == '__main__':
    main()
