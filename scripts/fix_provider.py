import os
filepath = r'c:\Users\ADEDAMOLA\Desktop\afrigen\services\provider_manager.py'
with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

target = """        if max_tokens:
            args["max_tokens"] = max_tokens
            
        response = self.client.chat.completions.create(**args)"""

replacement = """        if max_tokens:
            args["max_tokens"] = max_tokens
        if kwargs.get('response_format'):
            args["response_format"] = kwargs['response_format']
            
        response = self.client.chat.completions.create(**args)"""

content = content.replace(target, replacement)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print("Fixed provider_manager.py!")
