from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import random
from datetime import datetime, timedelta, timezone
from app.utils.i18n import get_text as _t

study = Blueprint('study', __name__)

def get_current_room_name():
    """Returns the room name based on the current system time (Taiwan UTC+8)."""
    # Force UTC+8 for consistent room naming
    hour = (datetime.now(timezone.utc) + timedelta(hours=8)).hour
    if 6 <= hour < 12:
        return "room_morning"
    elif 12 <= hour < 17:
        return "room_afternoon"
    elif 17 <= hour < 19:
        return "room_evening"
    else:
        return "room_night"

@study.route("/practice", methods=['GET', 'POST'])
@login_required
def practice():
    from app import db
    from app.models import Question, Mistake
    if request.method == 'POST':
        question_id = request.form.get('question_id')
        user_answer = request.form.get('answer')
        
        question = Question.query.get_or_404(question_id)
        is_correct = (user_answer == question.correct_answer)
        
        mistake = Mistake.query.filter_by(user_id=current_user.id, question_id=question_id).first()
        
        if is_correct:
            # SRS Logic for correct answer
            if mistake:
                mistake.srs_level = min(mistake.srs_level + 1, 7)
                intervals = [0, 1, 2, 4, 7, 14, 30, 60]
                mistake.last_interval = intervals[mistake.srs_level]
                mistake.next_review_date = datetime.now(timezone.utc) + timedelta(days=mistake.last_interval)
                if mistake.srs_level >= 4: # Consider resolved if reached a high level
                    mistake.is_resolved = True
                    from app.utils.i18n import get_text
                    flash(_t('msg_study_done', current_user.language), 'success')
                    
                    # Add Garden XP (SRS Level Bonus: 20 XP)
                    from app.utils.garden_helpers import add_garden_xp
                    add_garden_xp(20)
            
            # Continuous Garden XP (5 XP per correct answer)
            from app.utils.garden_helpers import add_garden_xp
            add_garden_xp(5)
            
            # Collaborative Garden Contribution
            try:
                from app.models import GroupMember, Group
                memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
                for m in memberships:
                    g = m.group_info
                    g.garden_exp += 10 # 10 exp per correct answer
                    # Level up logic: level * 1000 exp
                    next_level_exp = g.garden_level * 1000
                    if g.garden_exp >= next_level_exp:
                        g.garden_level += 1
                        # We could send a group message here, but skipping for now to keep it simple
            except Exception:
                pass

            db.session.commit()
        else:
            # SRS Logic for wrong answer
            if mistake:
                mistake.mistake_count += 1
                mistake.srs_level = max(mistake.srs_level - 1, 0) # Drop one level
                mistake.is_resolved = False
            else:
                mistake = Mistake(user_id=current_user.id, question_id=question_id)
                db.session.add(mistake)
            
            # Reset review clock for wrong answer
            mistake.next_review_date = datetime.now(timezone.utc) + timedelta(hours=1)
            db.session.commit()
            
        return jsonify({
            'correct': is_correct,
            'correct_answer': question.correct_answer,
            'explanation': question.explanation,
            'srs_level': mistake.srs_level if mistake else 0
        })

    # GET request - fetch random questions
    subject_filter = request.args.get('subject')
    query = Question.query
    if subject_filter:
        query = query.filter_by(subject=subject_filter)
        
    questions = query.all()
    if not questions:
        from app.utils.i18n import get_text
        flash(_t('msg_no_questions', current_user.language), 'info')
        return redirect(url_for('main.home'))
        
    question = random.choice(questions)
    return render_template('practice.html', title=_t('nav_practice', current_user.language), question=question)

@study.route("/mistakes")
@login_required
def mistakes():
    if not current_user.is_admin:
        flash(_t('msg_unauthorized', current_user.language), 'danger')
        return redirect(url_for('main.home'))
    from app.models import Mistake
    from app.utils.i18n import get_text
    mistake_records = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).all()
    return render_template('mistakes.html', title=_t('nav_mistakes', current_user.language), mistakes=mistake_records)


@study.route("/ai_vision", methods=['GET', 'POST'])
@login_required
def ai_vision():
    from app import db
    from app.models import Question, ChatSession, ChatMessage
    from app.utils.ai_helpers import analyze_question_image, parse_question_from_image, auto_tag_question, detect_duplicate_question
    
    if request.method == 'POST':
        if 'image' not in request.files:
            return jsonify({'error': _t('msg_no_image', current_user.language)}), 400
            
        file = request.files['image']
        if file.filename == '':
            return jsonify({'error': _t('msg_file_not_selected', current_user.language)}), 400
            
        image_bytes = file.read()
        
        # New mode: Quick OCR to Quiz
        mode = request.form.get('mode', 'analyze')
        if mode == 'ocr_to_quiz':
            from app.utils.ai_helpers import parse_question_from_image
            data = parse_question_from_image(image_bytes, lang=current_user.language)
            if 'error' in data:
                return jsonify(data), 500
            
            # Auto-tagging and Duplicate detection
            content = data.get('content_text', '')
            existing_questions = [q.content_text for q in Question.query.all()]
            if detect_duplicate_question(content, existing_questions):
                 return jsonify({'error': _t('msg_duplicate_question', current_user.language)}), 400
            
            tags = data.get('tags') or auto_tag_question(content)
            
            new_q = Question(
                subject=data.get('subject', _t('subject_all', current_user.language)),
                content_text=content,
                option_a=data.get('option_a'),
                option_b=data.get('option_b'),
                option_c=data.get('option_c'),
                option_d=data.get('option_d'),
                correct_answer=data.get('correct_answer', 'A'),
                explanation=data.get('explanation', ''),
                tags=tags
            )
            db.session.add(new_q)
            db.session.commit()
            return jsonify({'status': 'success', 'question_id': new_q.id, 'data': data})
        
        # Default analysis mode
        try:
            analysis_result = analyze_question_image(image_bytes, user=current_user, lang=current_user.language)
            
            if "[ERROR_INVALID_CONTENT]" in analysis_result:
                 return jsonify({'error': _t('msg_vision_invalid', current_user.language)}), 400
            
            # Create a chat session for the vision analysis
            session = ChatSession(user_id=current_user.id, title=_t('chat_session_vision', current_user.language))
            db.session.add(session)
            db.session.commit()
            
            ai_msg = ChatMessage(session_id=session.id, role='ai', content=analysis_result)
            db.session.add(ai_msg)
            db.session.commit()

            return jsonify({'result': analysis_result, 'session_id': session.id})
        except Exception as e:
            # Return JSON instead of causing a Flask 500 HTML so the frontend can display the exact error message
            return jsonify({'error': str(e)}), 200
        
    return render_template('ai_vision.html', title=_t('nav_vision', current_user.language))

@study.route("/analyze_mistake/<int:mistake_id>")
@login_required
def analyze_mistake(mistake_id):
    from app import db
    from app.models import Mistake, ChatSession, ChatMessage
    from app.utils.ai_helpers import get_ai_tutor_response, get_knowledge_graph_recommendation
    
    mistake = Mistake.query.get_or_404(mistake_id)
    if mistake.user_id != current_user.id:
        return jsonify({'error': _t('msg_unauthorized', current_user.language)}), 403
    
    question = mistake.question
    recommendation = get_knowledge_graph_recommendation(question.subject)
    
    prompt = _t('prompt_mistake_analysis', lang=current_user.language, content=question.content_text, correct=question.correct_answer, explanation=question.explanation)
    prompt += "\n\n" + _t('prompt_recommendation', lang=current_user.language, recommendation=recommendation)
    prompt += "\n" + _t('prompt_personality', lang=current_user.language, personality=(current_user.ai_personality or _t('ai_personality_gentle', current_user.language)))
    
    context_parts = []
    if current_user.bio:
        context_parts.append(f"學生個人簡介：{current_user.bio}")
    if current_user.learning_goals:
        context_parts.append(f"學生學習目標：{current_user.learning_goals}")
    context = "\n".join(context_parts)
    
    analysis = get_ai_tutor_response([], prompt, personality_key=current_user.ai_personality, context_summary=context, user=current_user)
    
    # Optional: Automatically create a chat session for this analysis
    session = ChatSession(user_id=current_user.id, title=f"{_t('chat_session_mistake', current_user.language)}: {question.content_text[:15]}...")
    db.session.add(session)
    db.session.commit()
    
    ai_msg = ChatMessage(session_id=session.id, role='ai', content=analysis)
    db.session.add(ai_msg)
    db.session.commit()

    return jsonify({'analysis': analysis, 'recommendation': recommendation, 'session_id': session.id})

@study.route("/api/generate_ai_question")
@login_required
def generate_question_api():
    from app import db
    from app.models import Question
    subject = request.args.get('subject', _t('subject_math', current_user.language))
    from app.utils.ai_helpers import generate_ai_quiz
    quiz_data = generate_ai_quiz(subject, lang=current_user.language)
    
    if 'error' in quiz_data:
        return jsonify(quiz_data), 500
        
    # Save to database
    new_q = Question(
        subject=subject,
        content_text=quiz_data.get('content_text'),
        option_a=quiz_data.get('option_a'),
        option_b=quiz_data.get('option_b'),
        option_c=quiz_data.get('option_c'),
        option_d=quiz_data.get('option_d'),
        correct_answer=quiz_data.get('correct_answer'),
        explanation=quiz_data.get('explanation'),
        tags=quiz_data.get('tags')
    )
    db.session.add(new_q)
    db.session.commit()
    
    return jsonify({'status': 'success', 'question_id': new_q.id, 'quiz': quiz_data})

@study.route("/tutor_chat", methods=['POST'])
@login_required
def tutor_chat():
    from app import db
    from app.models import ChatSession, ChatMessage, Mistake
    from app.utils.ai_helpers import get_ai_tutor_response
    try:
        user_msg = request.json.get('message', '')
        session_id = request.json.get('session_id')
        image_data = request.json.get('image', None)
        
        if not user_msg and not image_data:
            return jsonify({'error': _t('msg_empty_message', current_user.language)}), 400
            
        # Get or create session
        if session_id:
            session = ChatSession.query.get_or_404(session_id)
            if session.user_id != current_user.id:
                return jsonify({'error': _t('msg_unauthorized', current_user.language)}), 403
            
            # Persistent Vision: If no image in current request, try to find the last image in this session
            if not image_data:
                last_msg_with_image = ChatMessage.query.filter(
                    ChatMessage.session_id == session.id, 
                    ChatMessage.image_data != None
                ).order_by(ChatMessage.created_at.desc()).first()
                if last_msg_with_image:
                    image_data = last_msg_with_image.image_data
        else:
            session = ChatSession(user_id=current_user.id, title=(user_msg[:20] if user_msg else "Image Analysis"))
            db.session.add(session)
            db.session.commit()

        # Save user message
        user_chat_content = f"{user_msg}\n[附圖]" if image_data else user_msg
        user_chat = ChatMessage(session_id=session.id, role='user', content=user_chat_content, image_data=image_data)
        db.session.add(user_chat)
        db.session.commit()
        
        # Build comprehensive context
        context_parts = []
        if current_user.bio:
            context_parts.append(f"{_t('sys_prompt_background', current_user.language)}{current_user.bio}")
        if current_user.learning_goals:
            context_parts.append(f"{_t('sys_prompt_goals', current_user.language)}{current_user.learning_goals}")
            
        # Add mistake patterns to context
        try:
            recent_mistakes = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).limit(5).all()
            if recent_mistakes:
                mistake_subjects = list(set([m.question.subject for m in recent_mistakes]))
                context_parts.append(_t('sys_prompt_weakness', lang=current_user.language, subjects=', '.join(mistake_subjects)))
                # Also include the specific question if it's the start of a session
                if not session_id and len(recent_mistakes) > 0:
                    q = recent_mistakes[0].question
                    context_parts.append(_t('sys_prompt_priority', lang=current_user.language, content=q.content_text))
        except Exception:
            pass
            
        context = "\n".join(context_parts)

        # Convert session messages to Gemini format
        history_override = request.json.get('history')
        if history_override:
            recent_history = history_override
        else:
            try:
                history = [{'role': str(m.role), 'parts': [str(m.content)]} for m in session.messages]
                recent_history = history[:-1] if len(history) > 0 else []
            except Exception:
                recent_history = []

        # Time injection has been moved to ai_helpers.py system prompt to avoid constant reporting
        user_msg_with_time = user_msg

        # --- Admin-only chat commands ---
        cmd = user_msg.strip().lower()
        if current_user.is_admin:
            if cmd == '/antigravity':
                current_user.ai_personality = 'ai_antigravity'
                db.session.commit()
                return jsonify({'status': 'success', 'reply': '🚀 **Antigravity Mode 已啟動！**\n\n雪音已切換至「極效修復型」模式。所有對話將以 Antigravity 核心回應。\n\n輸入 `/normal` 可恢復為一般模式。(๑•̀ㅂ•́)و✧'})
            if cmd == '/normal':
                current_user.ai_personality = 'ai_gentle'
                db.session.commit()
                return jsonify({'status': 'success', 'reply': '🌸 **已恢復一般模式**\n\n雪音已切換回溫柔陪伴型。如需再次啟動 Antigravity，請輸入 `/antigravity`。'})
            if cmd == '/help':
                help_text = (
                    "🔧 **管理員專屬指令列表**\n\n"
                    "| 指令 | 功能 |\n"
                    "|------|------|\n"
                    "| `/antigravity` | 啟動 Antigravity 極效修復模式 |\n"
                    "| `/normal` | 恢復一般溫柔模式 |\n"
                    "| `/status` | 查看系統狀態 (API Key、用戶數等) |\n"
                    "| `/broadcast 訊息` | 發布全站公告 |\n"
                    "| `/clearkeys` | 清除所有失效的 API Key |\n"
                    "| `/coach` | 切換為魔鬼教練模式 |\n"
                    "| `/senior` | 切換為學長模式 |\n"
                    "| `/image 描述` | 生成圖片 |\n"
                    "| `/help` | 顯示此列表 |\n"
                )
                return jsonify({'status': 'success', 'reply': help_text})
            if cmd == '/status':
                from app.models import User, APIKeyTracker
                total_users = User.query.count()
                active_keys = APIKeyTracker.query.filter_by(is_active=True).count()
                total_keys = APIKeyTracker.query.count()
                import datetime
                now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                status_text = (
                    f"⚙️ **系統狀態報告**\n\n"
                    f"📅 目前時間：{now}\n"
                    f"👥 註冊用戶數：**{total_users}**\n"
                    f"🔑 API Key 總數：**{total_keys}** (活躍：**{active_keys}**)\n"
                    f"🎭 當前 AI 人格：**{current_user.ai_personality}**\n"
                )
                return jsonify({'status': 'success', 'reply': status_text})
            if user_msg.strip().lower().startswith('/broadcast '):
                msg_content = user_msg.strip()[11:]
                if msg_content:
                    from app.models import Announcement
                    ann = Announcement(title='📢 管理員公告', content=msg_content, created_by_id=current_user.id, is_ai_generated=False)
                    db.session.add(ann)
                    db.session.commit()
                    return jsonify({'status': 'success', 'reply': f'📢 **公告已發布！**\n\n內容：{msg_content}'})
            if cmd == '/clearkeys':
                from app.models import APIKeyTracker
                bad = APIKeyTracker.query.filter(APIKeyTracker.is_active == False).all()
                count = len(bad)
                for k in bad:
                    db.session.delete(k)
                db.session.commit()
                return jsonify({'status': 'success', 'reply': f'🗑️ **已清除 {count} 個失效 API Key**'})
            if cmd == '/coach':
                current_user.ai_personality = 'ai_coach'
                db.session.commit()
                return jsonify({'status': 'success', 'reply': '🔥 **魔鬼教練模式已啟動！**\n\n準備好接受嚴格督促了嗎？給我認真讀書！'})
            if cmd == '/senior':
                current_user.ai_personality = 'ai_guy'
                db.session.commit()
                return jsonify({'status': 'success', 'reply': '😎 **學長模式已啟動！**\n\n嘿嘿，學長我來陪你讀書囉～有什麼不懂的儘管問！'})

        if image_data:
            from app.utils.ai_helpers import generate_vision_with_fallback, VISION_RUTHLESS_PROMPT
            import base64
            # Image data is in data URI format: "data:image/jpeg;base64,/9j/4AAQSk..."
            if ',' in image_data:
                base64_str = image_data.split(',')[1]
            else:
                base64_str = image_data
            image_bytes = base64.b64decode(base64_str)
            
            # Prepend the ruthless vision instructions to ensure manual marks are filtered
            vision_prompt = f"{VISION_RUTHLESS_PROMPT}\n\n學生訊息：{user_msg_with_time}\n\n請根據圖片內容與上述分層指令進行解析。"
            
            # Use generate_vision_with_fallback directly
            reply = generate_vision_with_fallback(
                prompt=vision_prompt,
                image_bytes=image_bytes,
                system_instruction=context
            )
        else:
            reply = get_ai_tutor_response(recent_history, user_msg_with_time, personality_key=current_user.ai_personality, context_summary=context, user=current_user)
        
        # Save AI response
        try:
            ai_chat = ChatMessage(session_id=session.id, role='ai', content=reply)
            db.session.add(ai_chat)
            db.session.commit()
        except Exception:
            db.session.rollback()
        
        return jsonify({'reply': reply, 'session_id': session.id})
    except Exception as e:
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify({'reply': _t('msg_ai_offline', current_user.language).format(error=str(e)), 'error': str(e)}), 200

@study.route("/api/chat/sessions")
@login_required
def get_chat_sessions():
    from app.models import ChatSession
    sessions = ChatSession.query.filter_by(user_id=current_user.id).order_by(ChatSession.created_at.desc()).all()
    return jsonify([{'id': s.id, 'title': s.title, 'created_at': s.created_at.isoformat()} for s in sessions])

@study.route("/api/chat/history/<int:session_id>")
@login_required
def get_chat_history(session_id):
    from app.models import ChatSession
    session = ChatSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return jsonify({'error': _t('msg_unauthorized', current_user.language)}), 403
    messages = [{'role': m.role, 'content': m.content} for m in session.messages]
    return jsonify({'messages': messages})

@study.route("/lofi")
@login_required
def lofi_room():
    room_title = get_current_room_name()
    return render_template('lofi.html', title=room_title)

@study.route("/generate_roadmap", methods=['POST'])
@login_required
def generate_roadmap():
    from app import db
    from app.models import Mistake
    from app.utils.ai_helpers import generate_study_roadmap
    import json
    from datetime import datetime
    exam_name = request.json.get('exam_name', _t('exam_default_name', current_user.language))
    exam_date_str = request.json.get('exam_date')
    
    if not exam_date_str:
        return jsonify({'error': _t('msg_need_exam_date', current_user.language)}), 400
        
    # Build user context
    context_parts = []
    if current_user.bio:
        context_parts.append(f"學生個人簡介：{current_user.bio}")
    if current_user.learning_goals:
        context_parts.append(f"學生學習目標：{current_user.learning_goals}")
    
    # Add recent mistakes context
    try:
        recent_mistakes = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).limit(5).all()
        if recent_mistakes:
            subjects = list(set([m.question.subject for m in recent_mistakes]))
            context_parts.append(f"學生最近在這些科目有較多錯題：{', '.join(subjects)}")
    except Exception:
        pass
    
    context = "\n".join(context_parts)
    
    from app.utils.ai_helpers import generate_study_roadmap
    roadmap = generate_study_roadmap(exam_name, exam_date_str, user_context=context, lang=current_user.language)
    
    if roadmap:
        try:
            current_user.exam_date = datetime.strptime(exam_date_str, '%Y-%m-%d').date()
            current_user.study_plan_json = json.dumps(roadmap, ensure_ascii=False)
            db.session.commit()
            return jsonify({'status': 'success', 'roadmap': roadmap})
        except Exception as e:
            db.session.rollback()
            return jsonify({'error': _t('msg_roadmap_save_fail', current_user.language).format(error=str(e))}), 500
    else:
        return jsonify({'error': _t('msg_roadmap_gen_fail', current_user.language)}), 500

@study.route("/generate_exam")
@login_required
def generate_exam():
    from app.models import Mistake
    from app.utils.i18n import get_text
    mistakes = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).order_by(Mistake.mistake_count.desc()).limit(5).all()
    if not mistakes:
        flash(_t('msg_no_mistakes', current_user.language), "info")
        return redirect(url_for('study.practice'))
    return render_template('exam.html', title=_t('nav_exam', current_user.language), mistakes=mistakes)

@study.route("/api/study/personal_welcome")
@login_required
def personal_welcome():
    from app.utils.ai_helpers import generate_text_with_fallback
    
    context = ""
    if current_user.learning_goals:
        context += f"學生的學習目標是：{current_user.learning_goals}。"
    
    display_name = current_user.username
    if '_備份_' in display_name:
        display_name = '管理員'
        
    prompt = f"妳是雪音老師。請根據用戶的名字「{display_name}」和背景「{context}」寫一段 50 字以內的溫馨歡迎語。語氣要充滿關懷，提到與他們的目標相關的鼓勵內容。僅回傳歡迎語內容，不要有任何標題或引號。"
    
    try:
        # Use a consistent system instruction for the welcome message
        system_instr = "妳是一位溫柔的日系老師「雪音」，語氣親切溫馨，充滿正能量。嚴格保持在 50 字以內。務必使用繁體中文回答，絕對不可用簡體中文。"
        welcome_msg = generate_text_with_fallback(prompt, system_instruction=system_instr, user=current_user)
    except Exception:
        welcome_msg = f"歡迎回來，{display_name}同學！今天也要跟著雪音一起朝著您的目標努力喔！(◕‿◕✿)"
    
    return jsonify({'message': welcome_msg})


