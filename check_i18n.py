import os
import re
import sys

# Add the app directory to sys.path
sys.path.append(os.getcwd())

from app.utils.i18n import TRANSLATIONS

def check_i18n_completeness():
    templates_dir = os.path.join(os.getcwd(), 'app', 'templates')
    hardcoded_found = False
    
    # Chinese characters regex
    chinese_regex = re.compile(r'[\u4e00-\u9fff]')
    # Skip list for known Chinese strings that are NOT translatable or are already handled
    skip_list = [
        '管理員',
        '雪音老師',
        '領航員',
        '繁體中文',
        '日本語',
    ]

    for root, dirs, files in os.walk(templates_dir):
        for file in files:
            if file.endswith('.html'):
                file_path = os.path.join(root, file)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                    # Remove all _t('...') calls and jinja variables
                    content_clean = re.sub(r'\{\{.*?\}\}', '', content)
                    content_clean = re.sub(r'\{%.*?%\}', '', content_clean)
                    content_clean = re.sub(r'<!--.*?-->', '', content_clean) # Remove HTML comments
                    
                    lines = content_clean.split('\n')
                    for i, line in enumerate(lines):
                        matches = chinese_regex.findall(line)
                        if matches:
                            # Check if the match is in the skip list
                            is_ignored = False
                            for skip in skip_list:
                                if skip in line:
                                    is_ignored = True
                                    break
                            
                            if not is_ignored:
                                print(f"Potential hardcoded Chinese in {file}:{i+1}: {line.strip()}")
                                hardcoded_found = True

    if not hardcoded_found:
        print("Verification Success: No unhandled hardcoded Chinese strings found in templates.")
    else:
        print("Verification Failed: Hardcoded Chinese strings found.")

if __name__ == "__main__":
    check_i18n_completeness()
