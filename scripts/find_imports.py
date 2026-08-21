import os
import ast
import sys

def get_imports(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return set()
            
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])
    return imports

def main():
    root_dir = '.'
    all_imports = set()
    for root, dirs, files in os.walk(root_dir):
        if 'venv' in root or '.git' in root or '__pycache__' in root or '.gemini' in root:
            continue
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                all_imports.update(get_imports(filepath))
                
    # filter out stdlib
    import sysconfig
    stdlib = set(sys.builtin_module_names)
    stdlib_paths = sysconfig.get_paths()['stdlib']
    for root, dirs, files in os.walk(stdlib_paths):
        for file in files:
            if file.endswith('.py'):
                stdlib.add(file[:-3])
        for d in dirs:
            stdlib.add(d)
            
    third_party = all_imports - stdlib
    print("Found third party imports:")
    for imp in sorted(third_party):
        print(imp)

if __name__ == '__main__':
    main()
