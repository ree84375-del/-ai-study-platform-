import os

file_path = "C:/Users/Good PC/.gemini/antigravity/scratch/ai_study_platform/app/utils/ai_helpers.py"
# Normalize path
file_path = os.path.normpath(file_path)

with open(file_path, "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
skip = False
for i, line in enumerate(lines):
    # Detect the start of corruption
    if i > 800 and i < 900 and "'雪音-溫柔型': {" in line and "system_prompt" in lines[i+1]:
        # This is the ghost block. Skip until AI_PERSONALITIES
        skip = True
        # But we need to make sure the previous function was closed
        if i > 0 and "strip()" in lines[i-1]:
             # We should have closed generate_ai_quiz
             pass
        continue
    
    if skip:
        if "AI_PERSONALITIES = {" in line:
            skip = False
            # Insert the proper translate_omikuji before personalities
            new_lines.append("\n")
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
            new_lines.append("        response_text = generate_text_with_fallback(prompt)\n")
            new_lines.append("        import re\n")
            new_lines.append("        clean_text = response_text.strip()\n")
            new_lines.append("        if '```' in clean_text:\n")
            new_lines.append("            match = re.search(r'```(?:json)?\\s*(\\{.*?\\})\\s*```', clean_text, re.DOTALL)\n")
            new_lines.append("            if match: clean_text = match.group(1).strip()\n")
            new_lines.append("            else: clean_text = clean_text.replace('```json', '').replace('```', '').strip()\n")
            new_lines.append("        import json\n")
            new_lines.append("        json.loads(clean_text)\n")
            new_lines.append("        return clean_text\n")
            new_lines.append("    except Exception:\n")
            new_lines.append("        return omikuji_json_str\n\n")
            new_lines.append(line)
        continue
    
    # Fix the case where the ghost block started on the same line as valid code
    if i > 800 and i < 900 and "strip()" in line and "'雪音-溫柔型': {" in line:
        valid_part = line.split("'雪音-溫柔型': {")[0].strip()
        new_lines.append(f"            {valid_part}\n")
        new_lines.append("        elif '```' in clean_text:\n")
        new_lines.append("            clean_text = clean_text.split('```')[1].split('```')[0].strip()\n")
        new_lines.append("\n")
        new_lines.append("        return json.loads(clean_text)\n")
        new_lines.append("    except Exception as e:\n")
        new_lines.append("        return {'error': str(e)}\n")
        skip = True
        continue

    new_lines.append(line)

with open(file_path, "w", encoding="utf-8") as f:
    f.writelines(new_lines)

print("Repair v2 complete.")
