from datetime import datetime, timezone

from sqlalchemy import desc, func

from app import db
from app.models import (
    APIKeyTracker,
    AssignmentStatus,
    ChatSession,
    Daruma,
    Ema,
    Mistake,
    Omikuji,
    Question,
    User,
)


RANKS = [
    {"name": "見習生", "min_points": 0, "icon": "fa-seedling"},
    {"name": "初段", "min_points": 120, "icon": "fa-leaf"},
    {"name": "二段", "min_points": 320, "icon": "fa-mountain-sun"},
    {"name": "三段", "min_points": 680, "icon": "fa-torii-gate"},
    {"name": "免許皆傳", "min_points": 1200, "icon": "fa-crown"},
]


def _safe_count(query):
    try:
        return query.count()
    except Exception:
        db.session.rollback()
        return 0


def _safe_first(query):
    try:
        return query.first()
    except Exception:
        db.session.rollback()
        return None


def _safe_all(query):
    try:
        return query.all()
    except Exception:
        db.session.rollback()
        return []


def _make_card(key, title, subtitle, icon, tone, current, target, category, detail, cta_text, cta_url):
    target = max(1, int(target))
    current = max(0, int(current))
    unlocked = current >= target
    progress = 100 if unlocked else round((current / target) * 100)
    return {
        "key": key,
        "title": title,
        "subtitle": subtitle,
        "icon": icon,
        "tone": tone,
        "current": current,
        "target": target,
        "progress": progress,
        "unlocked": unlocked,
        "category": category,
        "detail": detail,
        "cta_text": cta_text,
        "cta_url": cta_url,
    }


def _rank_from_points(points):
    current = RANKS[0]
    next_rank = None
    for index, rank in enumerate(RANKS):
        if points >= rank["min_points"]:
            current = rank
            next_rank = RANKS[index + 1] if index + 1 < len(RANKS) else None

    if next_rank:
        span = max(1, next_rank["min_points"] - current["min_points"])
        progress = round(((points - current["min_points"]) / span) * 100)
        remaining = max(0, next_rank["min_points"] - points)
    else:
        progress = 100
        remaining = 0

    return {
        "current": current,
        "next": next_rank,
        "progress": max(0, min(100, progress)),
        "remaining": remaining,
    }


def _seasonal_event():
    month = datetime.now(timezone.utc).month
    if month in (3, 4, 5):
        return {
            "name": "春季櫻花衝刺",
            "theme": "每天完成一個小任務，讓神社櫻花逐步綻放。",
            "icon": "fa-spa",
            "tone": "plum",
        }
    if month in (6, 7, 8):
        return {
            "name": "夏日祭模考",
            "theme": "把模擬考當成祭典關卡，完成一回就收集一枚祭典印。",
            "icon": "fa-fire",
            "tone": "vermilion",
        }
    if month in (9, 10, 11):
        return {
            "name": "秋季複習御守",
            "theme": "讀講義、清錯題、補弱點，替考前狀態加上一枚守護。",
            "icon": "fa-leaf",
            "tone": "sage",
        }
    return {
        "name": "冬季會考倒數",
        "theme": "用倒數節奏穩定複習，把焦慮拆成每天可完成的格子。",
        "icon": "fa-snowflake",
        "tone": "indigo",
    }


def _milestone_definitions(metrics, links):
    return [
        ("daily_omikuji_1", "今日御神籤", "抽一次今日學習籤", "fa-scroll", "gold", metrics["omikuji"], 1, "daily", "每天抽籤可以把學習狀態變成一個小儀式。", "去抽籤", links["home"]),
        ("daily_omikuji_3", "三日籤巡禮", "累積 3 張學習籤", "fa-scroll", "gold", metrics["omikuji"], 3, "daily", "把開局儀式連續做三次，節奏就會開始成形。", "回首頁", links["home"]),
        ("daily_omikuji_7", "七福神籤", "累積 7 張學習籤", "fa-fan", "plum", metrics["omikuji"], 7, "daily", "七次小儀式會比一次爆衝更容易留下習慣。", "回首頁", links["home"]),
        ("daily_omikuji_14", "半月參拜", "累積 14 張學習籤", "fa-calendar-days", "sage", metrics["omikuji"], 14, "daily", "兩週的穩定感，是準備長跑的第一個訊號。", "回首頁", links["home"]),
        ("daily_omikuji_30", "月讀籤主", "累積 30 張學習籤", "fa-moon", "indigo", metrics["omikuji"], 30, "daily", "你已經把學習儀式變成日常的一部分。", "回首頁", links["home"]),
        ("streak_1", "今日不斷線", "連續學習 1 天", "fa-fire-flame-simple", "vermilion", metrics["streak"], 1, "daily", "不用一開始就完美，只要今天回來就是勝利。", "開始練習", links["practice"]),
        ("streak_3", "三日火種", "連續學習 3 天", "fa-fire", "vermilion", metrics["streak"], 3, "daily", "三天是一個火種，接下來要做的是保溫。", "開始練習", links["practice"]),
        ("streak_7", "一週燈籠", "連續學習 7 天", "fa-fire-burner", "gold", metrics["streak"], 7, "daily", "你已經點亮一整週的學習燈籠。", "開始練習", links["practice"]),
        ("streak_14", "雙週守夜", "連續學習 14 天", "fa-torii-gate", "indigo", metrics["streak"], 14, "daily", "穩定比猛衝更難，也更值得被記錄。", "開始練習", links["practice"]),
        ("streak_30", "月之修行者", "連續學習 30 天", "fa-crown", "gold", metrics["streak"], 30, "daily", "三十天的軌跡，是自己的第一本修行曆。", "開始練習", links["practice"]),
        ("ema_1", "第一塊繪馬", "寫下第一個願望或目標", "fa-tags", "sage", metrics["ema"], 1, "shrine", "把目標掛起來，會比只放在腦袋裡更容易被自己看見。", "寫繪馬", links["home"]),
        ("ema_3", "三願成形", "寫下 3 塊繪馬", "fa-feather", "sage", metrics["ema"], 3, "shrine", "多寫幾次，你會更知道自己真正想補強的是什麼。", "寫繪馬", links["home"]),
        ("ema_7", "七願繪馬架", "寫下 7 塊繪馬", "fa-place-of-worship", "gold", metrics["ema"], 7, "shrine", "你的願望架開始長出清楚的方向感。", "寫繪馬", links["home"]),
        ("ema_15", "願望織匠", "寫下 15 塊繪馬", "fa-hands-holding-circle", "plum", metrics["ema"], 15, "shrine", "把焦慮寫成可行動的願望，是一種很好的整理。", "寫繪馬", links["home"]),
        ("daruma_1", "達磨開眼", "立下一個達磨目標", "fa-bullseye", "vermilion", metrics["daruma"], 1, "shrine", "達磨適合放長期目標，例如會考衝刺、每天複習、完成一份講義。", "設定目標", links["home"]),
        ("daruma_3", "三尊達磨", "建立 3 個達磨目標", "fa-bullseye", "vermilion", metrics["daruma"], 3, "shrine", "目標不再只是口號，而是被你具體放上桌面。", "設定目標", links["home"]),
        ("daruma_5", "願望棚滿座", "建立 5 個達磨目標", "fa-layer-group", "gold", metrics["daruma"], 5, "shrine", "不同目標開始互相支撐，像一座完整的修行棚。", "設定目標", links["home"]),
        ("daruma_done_1", "雙眼達磨", "完成 1 個達磨目標", "fa-circle-check", "gold", metrics["completed_daruma"], 1, "shrine", "完成目標後替達磨補上另一隻眼，這會是一個很有感的收束。", "看達磨", links["home"]),
        ("daruma_done_3", "三願達成", "完成 3 個達磨目標", "fa-medal", "gold", metrics["completed_daruma"], 3, "shrine", "你已經證明自己能把目標推到終點。", "看達磨", links["home"]),
        ("daruma_done_5", "免許願主", "完成 5 個達磨目標", "fa-crown", "vermilion", metrics["completed_daruma"], 5, "shrine", "這不是運氣，是持續行動累積出的成果。", "看達磨", links["home"]),
        ("mistake_1", "錯題妖怪圖鑑", "收集第一題錯題", "fa-ghost", "plum", metrics["total_mistakes"], 1, "study", "錯題不是失敗，是妖怪現形。看見牠，才有機會把牠收服。", "去刷題", links["practice"]),
        ("mistake_5", "妖怪觀察員", "累積 5 題錯題", "fa-magnifying-glass-chart", "plum", metrics["total_mistakes"], 5, "study", "錯題開始形成圖像，也代表弱點可以被分類處理了。", "看錯題", links["mistakes"]),
        ("mistake_10", "弱點獵人", "累積 10 題錯題", "fa-crosshairs", "vermilion", metrics["total_mistakes"], 10, "study", "找到弱點不是壞事，這代表複習終於有靶心。", "看錯題", links["mistakes"]),
        ("mistake_25", "妖怪圖鑑編纂者", "累積 25 題錯題", "fa-book-skull", "plum", metrics["total_mistakes"], 25, "study", "你有足夠資料能看見自己最常掉進哪一種陷阱。", "看錯題", links["mistakes"]),
        ("mistake_50", "百鬼夜行前哨", "累積 50 題錯題", "fa-ghost", "indigo", metrics["total_mistakes"], 50, "study", "大量錯題如果被整理好，會變成最精準的複習地圖。", "看錯題", links["mistakes"]),
        ("resolved_1", "第一道淨化", "完成 1 題錯題複習", "fa-water", "sage", metrics["resolved_mistakes"], 1, "study", "重做錯題就是把知識漏洞補起來。", "開錯題本", links["mistakes"]),
        ("resolved_3", "弱點淨化", "完成 3 題錯題複習", "fa-water", "indigo", metrics["resolved_mistakes"], 3, "study", "把錯題重新做對，比單純看詳解更能補上破洞。", "開錯題本", links["mistakes"]),
        ("resolved_10", "十題祓除", "完成 10 題錯題複習", "fa-hand-sparkles", "gold", metrics["resolved_mistakes"], 10, "study", "十題代表你已經開始真正反擊弱點。", "開錯題本", links["mistakes"]),
        ("resolved_25", "淨化結界", "完成 25 題錯題複習", "fa-shield-heart", "sage", metrics["resolved_mistakes"], 25, "study", "越多錯題被清掉，考前焦慮就越少一點。", "開錯題本", links["mistakes"]),
        ("resolved_50", "妖怪封印師", "完成 50 題錯題複習", "fa-wand-magic-sparkles", "plum", metrics["resolved_mistakes"], 50, "study", "你已經把錯題從敵人變成了自己的訓練場。", "開錯題本", links["mistakes"]),
        ("assignment_1", "作業奉納印", "完成 1 份老師作業", "fa-book-open-reader", "sage", metrics["assignments"], 1, "study", "老師派出的任務完成後，會成為你的學習紀錄之一。", "開始刷題", links["practice"]),
        ("assignment_3", "三帖作業卷", "完成 3 份老師作業", "fa-clipboard-check", "indigo", metrics["assignments"], 3, "study", "固定完成作業，是最穩定的基礎訓練。", "開始刷題", links["practice"]),
        ("assignment_5", "奉納達人", "完成 5 份老師作業", "fa-scroll", "gold", metrics["assignments"], 5, "study", "你已經有一串能被看見的作業紀錄。", "開始刷題", links["practice"]),
        ("assignment_10", "課業守護者", "完成 10 份老師作業", "fa-book-bookmark", "vermilion", metrics["assignments"], 10, "study", "長期完成作業的人，通常也最容易在考前穩住。", "開始刷題", links["practice"]),
        ("ai_1", "雪音相談室", "建立 1 次 AI 對話紀錄", "fa-comments", "indigo", metrics["chat_sessions"], 1, "companion", "遇到卡住的地方，可以把它丟給 AI 助教拆解。", "找雪音", links["chat"]),
        ("ai_3", "三問入門", "建立 3 次 AI 對話紀錄", "fa-comment-dots", "indigo", metrics["chat_sessions"], 3, "companion", "會提問的人，通常比只硬背的人走得更遠。", "找雪音", links["chat"]),
        ("ai_10", "相談常連", "建立 10 次 AI 對話紀錄", "fa-robot", "sage", metrics["chat_sessions"], 10, "companion", "你開始把 AI 當成學習流程的一部分，而不是臨時救火。", "找雪音", links["chat"]),
        ("ai_30", "雪音同盟", "建立 30 次 AI 對話紀錄", "fa-user-astronaut", "plum", metrics["chat_sessions"], 30, "companion", "AI 助教已經成為你的固定學習夥伴。", "找雪音", links["chat"]),
        ("points_120", "初段之證", "修行點數達 120", "fa-award", "gold", metrics["points"], 120, "rank", "段位會把零散學習轉成長期成長線。", "看段位", links["achievements"]),
        ("points_320", "二段之證", "修行點數達 320", "fa-mountain-sun", "indigo", metrics["points"], 320, "rank", "你已經不只是開始，而是進入穩定累積期。", "看段位", links["achievements"]),
        ("points_680", "三段之證", "修行點數達 680", "fa-torii-gate", "sage", metrics["points"], 680, "rank", "學習路線開始有自己的骨架。", "看段位", links["achievements"]),
        ("points_1200", "免許皆傳", "修行點數達 1200", "fa-crown", "vermilion", metrics["points"], 1200, "rank", "你已經走到可以回頭指引別人的段位。", "看段位", links["achievements"]),
        ("sakura_180", "櫻花照料者", "修行點數達 180", "fa-tree", "sage", metrics["points"], 180, "shrine", "每天一點點學習都會讓樹長大。", "回神社", links["achievements"]),
        ("sakura_360", "含苞庭師", "修行點數達 360", "fa-seedling", "sage", metrics["points"], 360, "shrine", "你的學習樹已經有明顯生命力。", "回神社", links["achievements"]),
        ("sakura_720", "滿開守人", "修行點數達 720", "fa-spa", "plum", metrics["points"], 720, "shrine", "櫻花滿開時，代表許多小努力已經連成一片。", "回神社", links["achievements"]),
        ("sakura_1080", "夜櫻行者", "修行點數達 1080", "fa-moon", "indigo", metrics["points"], 1080, "shrine", "即使晚上補進度，也是一種溫柔但堅定的前進。", "回神社", links["achievements"]),
        ("season_80", "季節任務入門", "修行點數達 80", "fa-calendar-days", "gold", metrics["points"], 80, "seasonal", "完成季節活動的第一個小目標。", "看活動", links["achievements"]),
        ("season_200", "祭典參加者", "修行點數達 200", "fa-drum", "vermilion", metrics["points"], 200, "seasonal", "把複習做成活動，會比硬撐更容易持續。", "看活動", links["achievements"]),
        ("season_500", "御守收藏家", "修行點數達 500", "fa-gem", "sage", metrics["points"], 500, "seasonal", "每一枚御守都是你有回來學習的證明。", "看活動", links["achievements"]),
        ("season_900", "神社巡禮王", "修行點數達 900", "fa-torii-gate", "plum", metrics["points"], 900, "seasonal", "你已經能把題目、錯題、講義與 AI 串成完整巡禮。", "看活動", links["achievements"]),
    ]


def build_user_achievement_payload(user, url_builder):
    omikuji_count = _safe_count(Omikuji.query.filter_by(user_id=user.id))
    ema_count = _safe_count(Ema.query.filter_by(user_id=user.id))
    daruma_count = _safe_count(Daruma.query.filter_by(user_id=user.id))
    completed_daruma_count = _safe_count(Daruma.query.filter_by(user_id=user.id, is_completed=True))
    open_mistake_count = _safe_count(Mistake.query.filter_by(user_id=user.id, is_resolved=False))
    resolved_mistake_count = _safe_count(Mistake.query.filter_by(user_id=user.id, is_resolved=True))
    assignment_done_count = _safe_count(AssignmentStatus.query.filter_by(user_id=user.id, is_completed=True))
    chat_session_count = _safe_count(ChatSession.query.filter_by(user_id=user.id))
    active_daruma = _safe_first(
        Daruma.query.filter_by(user_id=user.id, is_completed=False).order_by(Daruma.created_at.desc())
    )

    total_mistakes = open_mistake_count + resolved_mistake_count
    streak = int(getattr(user, "current_streak", 0) or 0)
    base_points = (
        omikuji_count * 8
        + ema_count * 12
        + daruma_count * 20
        + completed_daruma_count * 80
        + resolved_mistake_count * 18
        + assignment_done_count * 28
        + chat_session_count * 10
        + streak * 6
    )
    rank = _rank_from_points(base_points)

    links = {
        "home": url_builder("main.home"),
        "practice": url_builder("study.practice"),
        "mistakes": url_builder("study.mistakes"),
        "chat": url_builder("main.chat"),
        "achievements": url_builder("main.achievements"),
    }
    metrics = {
        "omikuji": omikuji_count,
        "ema": ema_count,
        "daruma": daruma_count,
        "completed_daruma": completed_daruma_count,
        "total_mistakes": total_mistakes,
        "resolved_mistakes": resolved_mistake_count,
        "assignments": assignment_done_count,
        "chat_sessions": chat_session_count,
        "streak": streak,
        "points": base_points,
    }

    cards = [
        _make_card(
            "first_step",
            "入門朱印",
            "第一次踏進學習內所",
            "fa-torii-gate",
            "indigo",
            1,
            1,
            "daily",
            "帳號已建立，這枚朱印代表你正式開始自己的學習旅程。",
            "回首頁",
            links["home"],
        )
    ]
    cards.extend(_make_card(*definition) for definition in _milestone_definitions(metrics, links))

    unlocked_cards = [card for card in cards if card["unlocked"]]
    locked_cards = [card for card in cards if not card["unlocked"]]
    next_card = sorted(locked_cards, key=lambda card: card["progress"], reverse=True)[0] if locked_cards else None

    omamori = [
        {"name": "晨讀御守", "icon": "fa-sun", "tone": "gold", "unlocked": omikuji_count >= 1, "condition": "抽過今日學習籤", "effect": "每日開局更有儀式感"},
        {"name": "錯題淨化御守", "icon": "fa-water", "tone": "indigo", "unlocked": resolved_mistake_count >= 3, "condition": "完成 3 題錯題複習", "effect": "弱點整理速度提升"},
        {"name": "達磨願望御守", "icon": "fa-bullseye", "tone": "vermilion", "unlocked": daruma_count >= 1, "condition": "設定一個達磨目標", "effect": "長期目標更不容易散掉"},
        {"name": "相談室御守", "icon": "fa-comments", "tone": "sage", "unlocked": chat_session_count >= 1, "condition": "建立一次 AI 對話", "effect": "卡關時知道去哪裡問"},
    ]

    seals = [
        {"name": "國文朱印", "subject": "國文", "unlocked": False, "hint": "完成一回國文會考或一般練習後解鎖"},
        {"name": "英文朱印", "subject": "英文", "unlocked": False, "hint": "完成一回英文會考或一般練習後解鎖"},
        {"name": "數學朱印", "subject": "數學", "unlocked": False, "hint": "完成一回數學會考或一般練習後解鎖"},
        {"name": "錯題朱印", "subject": "弱點", "unlocked": resolved_mistake_count >= 3, "hint": "完成 3 題錯題複習後解鎖"},
        {"name": "達磨朱印", "subject": "願望", "unlocked": completed_daruma_count >= 1, "hint": "完成一個達磨目標後解鎖"},
    ]

    yokai = _build_yokai_collection(user.id, total_mistakes, resolved_mistake_count)
    sakura_level = min(5, max(1, base_points // 160 + 1))
    sakura = {
        "level": sakura_level,
        "growth": min(100, base_points % 160 * 100 // 160),
        "petals": min(48, 8 + sakura_level * 7 + len(unlocked_cards)),
        "state": ["新芽", "含苞", "初開", "滿開", "夜櫻"][sakura_level - 1],
    }

    total_points = sum(30 + min(card["target"], 1200) * 3 for card in unlocked_cards) + base_points
    summary = {
        "unlocked": len(unlocked_cards),
        "total": len(cards),
        "total_points": total_points,
        "completion_percent": round((len(unlocked_cards) / len(cards)) * 100) if cards else 0,
        "next_card": next_card,
        "active_daruma": active_daruma,
        "open_mistakes": open_mistake_count,
    }

    return {
        "cards": cards,
        "summary": summary,
        "rank": rank,
        "omamori": omamori,
        "seals": seals,
        "sakura": sakura,
        "yokai": yokai,
        "seasonal_event": _seasonal_event(),
        "filters": [
            {"key": "all", "label": "全部"},
            {"key": "daily", "label": "日課"},
            {"key": "shrine", "label": "神社"},
            {"key": "study", "label": "學習"},
            {"key": "rank", "label": "段位"},
            {"key": "companion", "label": "AI 助教"},
            {"key": "seasonal", "label": "季節"},
        ],
    }


def _build_yokai_collection(user_id, total_mistakes, resolved_mistakes):
    rows = _safe_all(
        db.session.query(Question.subject, func.count(Mistake.id))
        .join(Question, Question.id == Mistake.question_id)
        .filter(Mistake.user_id == user_id)
        .group_by(Question.subject)
        .order_by(desc(func.count(Mistake.id)))
        .limit(4)
    )
    primary_subject = rows[0][0] if rows else "尚未出現"
    return [
        {"name": "粗心鬼", "icon": "fa-face-dizzy", "unlocked": total_mistakes >= 1, "progress": min(100, total_mistakes * 25), "weakness": "先把題幹關鍵字圈起來。"},
        {"name": "閱讀陷阱鬼", "icon": "fa-book-skull", "unlocked": primary_subject in ("國文", "英文") or total_mistakes >= 4, "progress": min(100, total_mistakes * 16), "weakness": f"目前最常出沒：{primary_subject}。"},
        {"name": "單位鬼", "icon": "fa-ruler-combined", "unlocked": primary_subject in ("數學", "自然") or total_mistakes >= 6, "progress": min(100, total_mistakes * 12), "weakness": "遇到數字題先確認單位與條件。"},
        {"name": "復活鬼", "icon": "fa-ghost", "unlocked": resolved_mistakes >= 3, "progress": min(100, resolved_mistakes * 30), "weakness": "錯題重做三次後，牠就會變成你的圖鑑收藏。"},
    ]


def build_admin_achievement_payload():
    total_users = _safe_count(User.query)
    active_users = _safe_count(User.query.filter(User.last_active_at.isnot(None)))
    total_questions = _safe_count(Question.query)
    missing_answers = _safe_count(Question.query.filter((Question.correct_answer.is_(None)) | (Question.correct_answer == "")))
    missing_explanations = _safe_count(Question.query.filter((Question.explanation.is_(None)) | (Question.explanation == "")))
    missing_images = _safe_count(Question.query.filter((Question.content_image.is_(None)) | (Question.content_image == "")))
    total_mistakes = _safe_count(Mistake.query)
    unresolved_mistakes = _safe_count(Mistake.query.filter_by(is_resolved=False))

    duplicate_groups = 0
    try:
        duplicate_groups = (
            db.session.query(Question.content_text)
            .filter(Question.content_text.isnot(None))
            .group_by(Question.content_text)
            .having(func.count(Question.id) > 1)
            .count()
        )
    except Exception:
        db.session.rollback()

    api_rows = _safe_all(
        db.session.query(APIKeyTracker.status, func.count(APIKeyTracker.id))
        .group_by(APIKeyTracker.status)
        .order_by(APIKeyTracker.status)
    )
    api_status = [{"status": status or "unknown", "count": count} for status, count in api_rows]

    hotspots = _safe_all(
        db.session.query(Question.subject, func.count(Mistake.id))
        .join(Question, Question.id == Mistake.question_id)
        .group_by(Question.subject)
        .order_by(desc(func.count(Mistake.id)))
        .limit(6)
    )

    health_score = 100
    if total_questions:
        issue_count = missing_answers + missing_explanations + duplicate_groups
        health_score = max(0, round(100 - (issue_count / max(total_questions, 1)) * 100))

    return {
        "overview": {
            "total_users": total_users,
            "active_users": active_users,
            "total_questions": total_questions,
            "total_mistakes": total_mistakes,
            "unresolved_mistakes": unresolved_mistakes,
            "health_score": health_score,
        },
        "question_health": [
            {"label": "缺答案", "count": missing_answers, "tone": "vermilion"},
            {"label": "缺詳解", "count": missing_explanations, "tone": "gold"},
            {"label": "疑似重複題", "count": duplicate_groups, "tone": "plum"},
            {"label": "缺題目圖片", "count": missing_images, "tone": "sage"},
        ],
        "api_status": api_status,
        "hotspots": [{"subject": subject or "未分類", "count": count} for subject, count in hotspots],
        "seasonal_event": _seasonal_event(),
        "achievement_templates": [
            {"name": "段位升級", "status": "已上架", "detail": "依照修行點數自動判定見習生、初段、二段、三段與免許皆傳。"},
            {"name": "御守收藏", "status": "已上架", "detail": "依抽籤、錯題複習、達磨目標與 AI 對話解鎖。"},
            {"name": "朱印帳", "status": "已上架", "detail": "先連動錯題與達磨，後續可接會考、一般練習與講義閱讀。"},
            {"name": "季節活動", "status": "已上架", "detail": "依季節切換櫻花衝刺、夏日祭、秋季御守與冬季倒數。"},
            {"name": "錯題妖怪圖鑑", "status": "已上架", "detail": "把錯題弱點轉為可視化妖怪，協助學生重練。"},
        ],
        "admin_actions": [
            {"title": "題庫健康檢查", "detail": "檢查缺圖、缺答案、缺詳解與疑似重複題。", "icon": "fa-heart-pulse"},
            {"title": "題目審核系統", "detail": "問題題目先進待審，不直接上架到正式刷題流程。", "icon": "fa-clipboard-check"},
            {"title": "AI 使用量監控", "detail": "查看 API key 狀態、錯誤率與慢回覆風險。", "icon": "fa-gauge-high"},
            {"title": "AI 三層回答架構", "detail": "固定規則、RAG 查資料、模型生成分層處理，減少要回不回。", "icon": "fa-layer-group"},
            {"title": "RAG 與來源標記", "detail": "AI 回答前先查講義、題庫與詳解，並標示參考來源。", "icon": "fa-database"},
            {"title": "任務佇列", "detail": "大量 OCR、詳解生成與圖片修復改成背景任務，不卡住網站。", "icon": "fa-list-check"},
            {"title": "AI 快取與降級", "detail": "同題詳解不重複燒 API，主模型失敗時改走備援模板。", "icon": "fa-rotate"},
            {"title": "公告管理", "detail": "發布首頁公告、維護通知與課程公告。", "icon": "fa-bullhorn"},
            {"title": "講義管理", "detail": "依科目、章節、小節上架講義，並連動同章節刷題。", "icon": "fa-book-open"},
            {"title": "模擬考管理", "detail": "設定題數、時間、科目、開放期間與交卷規則。", "icon": "fa-file-pen"},
            {"title": "錯題分析總覽", "detail": "查看全站最常錯題、最弱章節與需要補強的題型。", "icon": "fa-chart-simple"},
            {"title": "活動管理", "detail": "建立限時任務、班級挑戰與排行榜。", "icon": "fa-calendar-days"},
            {"title": "角色氣泡設定", "detail": "管理員金色、一般用戶藍色、訪客紅色，只用在歡迎語。", "icon": "fa-comments"},
            {"title": "備份還原", "detail": "題庫與模板正式刪改前先保留可回復版本。", "icon": "fa-box-archive"},
        ],
    }
