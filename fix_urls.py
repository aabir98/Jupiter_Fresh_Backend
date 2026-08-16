import os
import glob

directory = "/Users/macofdevil/Desktop/Jupiter_fresh_main  /Jupiter_Fresh_Frontend/src/admin"
jsx_files = glob.glob(os.path.join(directory, "*.jsx"))

for file in jsx_files:
    with open(file, 'r') as f:
        content = f.read()
    
    if 'https://api.tajacart.in' in content:
        new_content = content.replace('https://api.tajacart.in', 'http://127.0.0.1:8000')
        with open(file, 'w') as f:
            f.write(new_content)
        print(f"Updated {file}")
