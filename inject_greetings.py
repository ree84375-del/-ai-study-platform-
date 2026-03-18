# -*- coding: utf-8 -*-
import re
import sys

file_path = "app/utils/i18n.py"
with open(file_path, "r", encoding="utf-8") as f:
    orig_content = f.read()

greetings_zh_admin = [
    '歡迎管理者 {username} 蒞臨！巡視辛苦了～✨',
    '{username} 您好！雪音隨時待命喔～👑',
    '最高權限者 {username} 上線啦！一切都在掌握中！👑',
    '管理者 {username} 辛苦了！有什麼任務交給雪音嗎？✨',
    '見過 {username} 管理員！系統運作一切正常喔～🚀',
    '歡迎回來，{username} 大大！有需要幫忙的地方嗎？✨',
    '{username} 管理員降臨！大家快乖乖站好～👑',
    '巡查辛苦啦 {username}！喝杯茶休息一下吧🍵',
    '系統狀態：完美！因為 {username} 管理員回來了！✨',
    '{username} 您好！今天也要守護這裡的和平喔～🕊️',
    '權限確認完畢！歡迎 {username} 進入管理員模式👑',
    '為您服務是我的榮幸，{username} 管理員！✨',
    '歡迎 {username}！這裡的大家都很用功喔～📚',
    '{username} 管理員好！雪音已經準備好接受指令了！🚀',
    '全場肅靜！{username} 管理員來啦～👑'
]

greetings_zh_teacher = [
    '老師 {username} 您好！今天要帶領大家學習什麼呢？🍎',
    '歡迎 {username} 老師！跟大家打個招呼吧～✨',
    '{username} 老師辛苦了！學生們都在等您喔！📚',
    '快看！是 {username} 老師來了！大家快坐好～🍎',
    '{username} 老師好！今天要準備哪些講義呢？📝',
    '歡迎 {username} 老師！今天的課程一定也很精彩！✨',
    '{username} 老師上線囉！有什麼教學任務交給雪音嗎？🍎',
    '大家快來聽課啦！{username} 老師來了～📚',
    '{username} 老師，喝杯咖啡提提神吧！☕',
    '歡迎 {username} 老師！今天要傳授什麼秘笈呢？✨',
    '{username} 老師好！學生們都很期待您的指導喔！🍎',
    '{username} 老師辛苦啦！休息一下再繼續備課吧～🍵',
    '見過 {username} 老師！雪音隨時準備好當您的小助手！✨',
    '{username} 老師來了！大家準備好筆記本了嗎？📝',
    '歡迎 {username} 老師！今天的教學也要順順利利喔！🍎'
]

greetings_zh_student = [
    '嗨 {username}！很高興見到你，準備好開始學習了嗎？(๑•̀ㅂ•́)و✧',
    '歡迎回來，{username}！今天也要一起加油喔～🌸',
    '{username} 來到討論區了！大家掌聲歡迎～👏',
    '看到 {username} 今天也來學習，雪音好開心！✨',
    '{username} 同學好！今天想挑戰什麼題目呢？📚',
    '歡迎 {username}！讓我們一起朝目標邁進吧！🚀',
    '{username} 上線啦！今天也要元氣滿滿喔！☀️',
    '嗨 {username}！有不懂的地方隨時問雪音喔～🌸',
    '{username} 終於來了！大家都在等你呢！👏',
    '歡迎回歸學習的行列，{username}！我們一起衝刺吧！✨',
    '{username} 同學辛苦了！喝口水再繼續吧～💧',
    '{username} 來啦！今天的學習目標是什麼呢？🎯',
    '看到 {username} 就覺得充滿幹勁！一起加油！(๑•̀ㅂ•́)و✧',
    '嗨 {username}！今天也要把知識通通裝進腦袋裡喔！🧠',
    '歡迎 {username}！學習路上有我們陪你～🌸'
]

greetings_zh_guest = [
    '歡迎訪客 {username}！隨意看看，有問題可以問我喔～✨',
    '嗨 {username}！歡迎來到我們的學習空間～🍃',
    '是新面孔呢！歡迎 {username} 來到這裡！🌸',
    '{username} 您好！希望您在這裡能找到喜歡的內容～✨',
    '歡迎 {username}！不要害羞，大家都很友善喔！👋',
    '嗨 {username}！有什麼需要雪音幫忙導覽的嗎？🍃',
    '{username} 訪客您好！祝您參觀愉快！✨',
    '歡迎 {username}！也許這裡就是您一直在尋找的學習樂園喔！🌸',
    '初次見面，{username}！我是導航員雪音，請多指教！🍃',
    '{username} 您好！如果您喜歡這裡，隨時歡迎註冊加入我們喔！✨',
    '歡迎 {username}！慢慢逛，如果有問題隨時呼叫我！👋',
    '嗨 {username}！這裡有很多豐富的學習資源喔！🍃',
    '{username} 訪客來訪！大家掌聲歡迎～👏',
    '歡迎 {username}！希望這裡的環境能讓您感到放鬆～🌸',
    '{username} 您好！有什麼想了解的，雪音都可以為您解答喔！✨'
]

greetings_ja_admin = [
    '管理者 {username} 様、ようこそ！巡回お疲れ様です✨',
    '管理者 {username} さん！いつでも指示をお待ちしています👑',
    '最高権限者 {username} 様がオンラインです！すべて順調です！👑',
    '管理者 {username} さん、何か雪音にお手伝いできる任務はありますか？✨',
    'ようこそ {username} 管理者様！システムは正常に稼働中です～🚀',
    'お帰りなさい、{username} 様！何かご用命は？✨',
    '{username} 管理者様が降臨されました！みんな姿勢を正して～👑',
    '巡視お疲れ様です {username} 様！お茶でもいかがですか🍵',
    'システムステータス：完璧！なぜなら {username} 管理者様が戻られたからです！✨',
    '{username} 様、こんにちは！今日もここの平和を守ってくださいね🕊️',
    '権限確認完了！{username} 様、管理者モードへようこそ👑',
    'お仕えできて光栄です、{username} 管理者様！✨',
    'ようこそ {username} 様！みんな一生懸命勉強していますよ～📚',
    '{username} 管理者様！雪音はいつでもコマンドを受付可能です！🚀',
    '静粛に！{username} 管理者様のお出ましです～👑'
]

greetings_ja_teacher = [
    '{username} 先生、こんにちは！今日は何を教えに来てくれましたか？🍎',
    '{username} 先生、ようこそ！皆に挨拶しましょう✨',
    '{username} 先生お疲れ様です！生徒たちが待っていますよ！📚',
    '見て！{username} 先生が来たよ！みんな席について～🍎',
    '{username} 先生！今日はどんな教材を準備しますか？📝',
    'ようこそ {username} 先生！今日の授業もきっと素晴らしいですね！✨',
    '{username} 先生がオンラインです！雪音に何かお手伝いはありますか？🍎',
    'みんな授業が始まるよ！{username} 先生が来ました～📚',
    '{username} 先生、コーヒーを飲んでリフレッシュしてください！☕',
    'ようこそ {username} 先生！今日はどんな秘伝を伝授してくれますか？✨',
    '{username} 先生、こんにちは！生徒たちは先生の指導を楽しみにしています！🍎',
    '{username} 先生お疲れ様です！少し休んでから授業の準備をしましょう～🍵',
    'ようこそ {username} 先生！雪音はいつでも先生の助手になる準備ができています！✨',
    '{username} 先生が来ました！みんなノートの準備はいいですか？📝',
    'ようこそ {username} 先生！今日の授業もスムーズに進みますように！🍎'
]

greetings_ja_student = [
    'やっほー {username}！準備はいい？一緒に勉強しよう！(๑•̀ㅂ•́)و✧',
    'お帰りなさい {username}！今日も一日頑張ろうね🌸',
    '{username} さんが掲示板に来たよ！皆歓迎してね～👏',
    '今日も {username} が勉強に来てくれて、雪音はうれしい！✨',
    '{username} さん、こんにちは！今日はどの問題に挑戦する？📚',
    'ようこそ {username}！一緒に目標に向かって進もう！🚀',
    '{username} がオンラインになったよ！今日も元気いっぱいでいこう！☀️',
    'やっほー {username}！わからないことがあったらいつでも聞いてね～🌸',
    '{username} がやっと来たね！みんな待ってたよ！👏',
    'お帰りなさい、学習の道へ {username}！一緒にスパートをかけよう！✨',
    '{username} さんお疲れ様！水を飲んでから続けよう～💧',
    '{username} が来た！今日の学習目標は何かな？🎯',
    '{username} を見るとやる気が出る！一緒に頑張ろう！(๑•̀ㅂ•́)و✧',
    'やっほー {username}！今日も知識をたくさん頭に詰め込もう！🧠',
    'ようこそ {username}！学習の旅には私たちがついているよ～🌸'
]

greetings_ja_guest = [
    'ゲストの {username} さん、ようこそ！ゆっくり見ていってくださいね✨',
    '訪客 {username} さん、こんにちは！学習コミュニティへようこそ🍃',
    '新しい顔ですね！{username} さん、ここへようこそ！🌸',
    '{username} さん、こんにちは！ここで好きなコンテンツを見つけてくださいね～✨',
    'ようこそ {username} さん！恥ずかしがらないで、みんなフレンドリーですよ！👋',
    'やっほー {username} さん！雪音に案内してほしいところはありますか？🍃',
    '{username} ゲスト様、こんにちは！ごゆっくりお楽しみください！✨',
    'ようこそ {username} さん！ひょっとすると、ここがあなたが探していた学習の楽園かもしれませんよ！🌸',
    '初めまして、{username} さん！私はナビゲーターの雪音です。よろしくお願いします！🍃',
    '{username} さん、こんにちは！ここが気に入ったら、いつでも登録して仲間に加わってくださいね！✨',
    'ようこそ {username} さん！ゆっくり回って、質問があればいつでも呼んでください！👋',
    'やっほー {username} さん！ここには豊富な学習リソースがたくさんありますよ！🍃',
    '{username} ゲスト様が来訪されました！皆様、拍手でお迎えを～👏',
    'ようこそ {username} さん！ここの環境でリラックスしていただければ幸いです～🌸',
    '{username} さん、こんにちは！知りたいことがあれば、雪音が何でもお答えしますよ！✨'
]

greetings_en_admin = [
    'Welcome, Admin {username}! Thanks for checking in! ✨',
    'Hello Admin {username}! I\\'m ready for your instructions! 👑',
    'Supreme Commander {username} is online! Everything is under control! 👑',
    'Good work, Admin {username}! Any tasks for Yukine today? ✨',
    'Greetings, Admin {username}! System operations are completely normal! 🚀',
    'Welcome back, boss {username}! Need any assistance? ✨',
    'Admin {username} has arrived! Everyone stand at attention! 👑',
    'Thanks for inspecting the site, {username}! Grab a cup of tea! 🍵',
    'System status: Flawless! Because Admin {username} is back! ✨',
    'Hello {username}! Please protect the peace of this place today too! 🕊️',
    'Privileges verified! Welcome to Admin Mode, {username}! 👑',
    'It is an honor to serve you, Admin {username}! ✨',
    'Welcome, {username}! Everyone is studying hard here! 📚',
    'Hello Admin {username}! Yukine is ready to receive commands! 🚀',
    'Order in the room! Admin {username} is here! 👑'
]

greetings_en_teacher = [
    'Hello Teacher {username}! What are we learning today? 🍎',
    'Welcome, {username} Sensei! Care to say hi to the group? ✨',
    'Good work, Teacher {username}! The students are waiting for you! 📚',
    'Look! Teacher {username} is here! Everyone take your seats! 🍎',
    'Hello Teacher {username}! What materials are we preparing today? 📝',
    'Welcome Teacher {username}! Today\\'s lesson will surely be amazing! ✨',
    'Teacher {username} is online! Any teaching tasks for Yukine? 🍎',
    'Gather around for class! Teacher {username} has arrived! 📚',
    'Teacher {username}, grab a coffee and refresh yourself! ☕',
    'Welcome Teacher {username}! What secrets will you teach today? ✨',
    'Hello Teacher {username}! The students are excited for your guidance! 🍎',
    'Great job Teacher {username}! Take a short break before prepping your next class! 🍵',
    'Greetings Teacher {username}! Yukine is always ready to be your assistant! ✨',
    'Teacher {username} is here! Does everyone have their notebooks ready? 📝',
    'Welcome Teacher {username}! May today\\'s teaching go smoothly! 🍎'
]

greetings_en_student = [
    'Hey {username}! Ready to dive into some learning? (๑•̀ㅂ•́)و✧',
    'Welcome back, {username}! Let\\'s do our best today! 🌸',
    'Look who\\'s here! Welcome, {username}! 👏',
    'Yukine is so happy to see {username} studying again today! ✨',
    'Hello {username}! What problems do you want to challenge today? 📚',
    'Welcome {username}! Let\\'s move towards our goals together! 🚀',
    '{username} is online! Let\\'s be full of energy today too! ☀️',
    'Hey {username}! Ask Yukine anytime if you have questions! 🌸',
    '{username} is finally here! Everyone was waiting for you! 👏',
    'Welcome back to studying, {username}! Let\\'s sprint together! ✨',
    'Good work, {username}! Take a sip of water and keep going! 💧',
    '{username} is here! What is our study goal today? 🎯',
    'Seeing {username} pumps me up! Let\\'s do this! (๑•̀ㅂ•́)و✧',
    'Hey {username}! Let\\'s pack our brains with knowledge today! 🧠',
    'Welcome {username}! We\\'re with you on this learning journey! 🌸'
]

greetings_en_guest = [
    'Welcome, Guest {username}! Feel free to look around! ✨',
    'Hi {username}! Hope you enjoy our little learning hub! 🍃',
    'A new face! Welcome to the site, {username}! 🌸',
    'Hello {username}! I hope you find content you like here! ✨',
    'Welcome {username}! Don\\'t be shy, everyone is friendly! 👋',
    'Hey {username}! Do you need Yukine to show you around? 🍃',
    'Hello Guest {username}! Have a pleasant visit! ✨',
    'Welcome {username}! Perhaps this is the learning paradise you\\'ve been searching for! 🌸',
    'Nice to meet you, {username}! I\\'m your navigator Yukine. Nice to work with you! 🍃',
    'Hello {username}! If you like it here, you are always welcome to register and join us! ✨',
    'Welcome {username}! Take your time browsing, and call me if you have questions! 👋',
    'Hey {username}! We have tons of rich learning resources here! 🍃',
    'Guest {username} is visiting! Let\\'s give them a round of applause! 👏',
    'Welcome {username}! I hope our environment helps you relax! 🌸',
    'Hello {username}! Yukine can answer whatever you want to know! ✨'
]

def build_block(admin, teacher, student, guest):
    lines = []
    lines.append(f"        'nav_label_yukine': '雪音老師',")
    for i, t in enumerate(admin):
        lines.append(f"        'yukine_welcome_admin_{i+1}': '{t}',")
    for i, t in enumerate(teacher):
        lines.append(f"        'yukine_welcome_teacher_{i+1}': '{t}',")
    for i, t in enumerate(student):
        lines.append(f"        'yukine_welcome_student_{i+1}': '{t}',")
    for i, t in enumerate(guest):
        lines.append(f"        'yukine_welcome_guest_{i+1}': '{t}',")
    return "\\n".join(lines)
    
zh_block = build_block(greetings_zh_admin, greetings_zh_teacher, greetings_zh_student, greetings_zh_guest)
ja_block = build_block(greetings_ja_admin, greetings_ja_teacher, greetings_ja_student, greetings_ja_guest)
en_block = build_block(greetings_en_admin, greetings_en_teacher, greetings_en_student, greetings_en_guest)

lines = orig_content.split("\\n")
new_lines = []

in_zh = False
in_ja = False
in_en = False

for line in lines:
    if line.strip() == "'zh': {": in_zh = True
    elif line.strip() == "'ja': {": in_ja = True
    elif line.strip() == "'en': {": in_en = True
    
    # Filter out old yukine strings
    if 'yukine_welcome_' in line or 'nav_label_yukine' in line:
        continue
        
    # Inject at the end of each dict block
    if line.strip() == "}," and line.startswith("    }"):
        if in_zh:
            new_lines.append(zh_block)
            in_zh = False
        elif in_ja:
            new_lines.append(ja_block)
            in_ja = False
        elif in_en:
            new_lines.append(en_block)
            in_en = False
            
    # if it's the very last line '}' (end of TRANSLATIONS) and we are in_en
    if line.strip() == "}" and line.startswith("}"):
        if in_en:
            new_lines.append(en_block)
            in_en = False
    
    new_lines.append(line)

with open(file_path, "w", encoding="utf-8") as f:
    f.write("\\n".join(new_lines))

print("Successfully injected 135 new greeting translations!")
