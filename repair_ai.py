import os

file_path = r"c:\Users\Good PC\.gemini\antigravity\scratch\ai_study_platform\app\utils\ai_helpers.py"

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    # Fix the corrupted line 828 (1-indexed is 827)
    if 'clean_text.split(\'```json\')[1].split(\'```\')[0].strip()' in line and "'雪音-溫柔型': {" in line:
        new_lines.append(line.split("'雪音-溫柔型': {")[0].strip() + "\n")
        new_lines.append("        elif '```' in clean_text:\n")
        new_lines.append("            clean_text = clean_text.split('```')[1].split('```')[0].strip()\n")
        new_lines.append("\n")
        new_lines.append("        return json.loads(clean_text)\n")
        new_lines.append("    except Exception as e:\n")
        new_lines.append("        return {'error': str(e)}\n\n")
        new_lines.append("def translate_omikuji(omikuji_json_str, target_lang='zh'):\n")
        new_lines.append("    \"\"\"Translates the omikuji JSON into the target language.\"\"\"\n")
        new_lines.append("    try:\n")
        new_lines.append("        lang_map = {'ja': 'Japanese', 'en': 'English', 'zh': 'Traditional Chinese'}\n")
        new_lines.append("        target_lang_name = lang_map.get(target_lang, 'Traditional Chinese')\n")
        new_lines.append("        prompt = f\"\"\"\n")
        new_lines.append("        You are a specialized translation engine for a Japanese Shrine system.\n")
        new_lines.append("        Convert the following JSON string into {target_lang_name}.\n\n")
        new_lines.append("        INPUT JSON:\n")
        new_lines.append("        {omikuji_json_str}\n\n")
        new_lines.append("        RULES:\n")
        new_lines.append("        1. Keep the JSON keys (lucky_color, lucky_item, lucky_subject, advice) EXACTLY as they are.\n")
        new_lines.append("        2. DO NOT return the original Chinese if the target is Japanese.\n")
        new_lines.append("        3. Use natural {target_lang_name} terminology.\n")
        new_lines.append("        4. Tone: Gentle, like a shrine maiden (Miko).\n\n")
        new_lines.append("        Return ONLY the raw JSON string.\n")
        new_lines.append("        \"\"\"\n")
        skip = True # Skip everything until AI_PERSONALITIES
        continue
    
    if skip:
        if "AI_PERSONALITIES = {" in line:
            skip = False
            new_lines.append(line)
        continue
    
    new_lines.append(line)

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Repair complete.")
