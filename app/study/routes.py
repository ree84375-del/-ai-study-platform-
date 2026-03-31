from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import random
import json
import os
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
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


PRACTICE_SUBJECTS = [
    {'slug': 'all', 'label': '\u5168\u90e8', 'icon': 'fa-globe', 'aliases': ['all', '\u5168\u90e8']},
    {'slug': 'chinese', 'label': '\u570b\u6587', 'icon': 'fa-book-open', 'aliases': ['\u570b\u6587', '\u4e2d\u6587', 'Chinese', 'subject_chinese', 'subject_chinese_short']},
    {'slug': 'english', 'label': '\u82f1\u6587', 'icon': 'fa-language', 'aliases': ['\u82f1\u6587', 'English', 'subject_english', 'subject_english_short']},
    {'slug': 'math', 'label': '\u6578\u5b78', 'icon': 'fa-calculator', 'aliases': ['\u6578\u5b78', 'Math', 'subject_math', 'subject_math_short']},
    {'slug': 'social', 'label': '\u793e\u6703', 'icon': 'fa-users', 'aliases': ['\u793e\u6703', 'Social']},
    {'slug': 'geography', 'label': '\u5730\u7406', 'icon': 'fa-map-location-dot', 'aliases': ['\u5730\u7406', 'Geography']},
    {'slug': 'history', 'label': '\u6b77\u53f2', 'icon': 'fa-landmark', 'aliases': ['\u6b77\u53f2', 'History']},
    {'slug': 'civics', 'label': '\u516c\u6c11', 'icon': 'fa-scale-balanced', 'aliases': ['\u516c\u6c11', 'Civics']},
    {'slug': 'science', 'label': '\u81ea\u7136', 'icon': 'fa-leaf', 'aliases': ['\u81ea\u7136', 'Science', 'Sciences']},
    {'slug': 'physics', 'label': '\u7269\u7406', 'icon': 'fa-atom', 'aliases': ['\u7269\u7406', 'Physics']},
    {'slug': 'chemistry', 'label': '\u5316\u5b78', 'icon': 'fa-flask', 'aliases': ['\u5316\u5b78', 'Chemistry']},
    {'slug': 'integrated_science', 'label': '\u7406\u5316', 'icon': 'fa-magnet', 'aliases': ['\u7406\u5316']},
    {'slug': 'earth_science', 'label': '\u5730\u79d1', 'icon': 'fa-earth-asia', 'aliases': ['\u5730\u79d1', 'Earth Science']},
    {'slug': 'japanese', 'label': '\u65e5\u6587', 'icon': 'fa-torii-gate', 'aliases': ['\u65e5\u6587', 'Japanese']},
]

PRACTICE_SUBJECT_GROUPS = [
    {
        'key': 'main',
        'label': '\u4e3b\u79d1',
        'description': '\u5148\u5f9e\u570b\u82f1\u6578\u958b\u59cb\uff0c\u9019\u5340\u662f\u6700\u5e38\u7528\u7684\u6838\u5fc3\u7df4\u7fd2\u3002',
        'slugs': ['chinese', 'english', 'math'],
    },
    {
        'key': 'social',
        'label': '\u793e\u6703',
        'description': '\u6b77\u53f2\u3001\u5730\u7406\u3001\u516c\u6c11\u8207\u7d9c\u5408\u793e\u6703\u90fd\u6536\u5728\u9019\u88e1\uff0c\u627e\u79d1\u76ee\u6703\u66f4\u5feb\u3002',
        'slugs': ['history', 'geography', 'civics', 'social'],
    },
    {
        'key': 'science',
        'label': '\u81ea\u7136',
        'description': '\u81ea\u7136\u3001\u7269\u7406\u3001\u5316\u5b78\u3001\u7406\u5316\u8207\u5730\u79d1\u96c6\u4e2d\u5728\u9019\u5340\uff0c\u4e0d\u6703\u518d\u6563\u6210\u4e00\u7247\u3002',
        'slugs': ['science', 'physics', 'chemistry', 'integrated_science', 'earth_science'],
    },
    {
        'key': 'other',
        'label': '\u5176\u4ed6',
        'description': '\u65e5\u6587\u548c\u5f8c\u7e8c\u65b0\u589e\u7684\u5ef6\u4f38\u79d1\u76ee\u90fd\u6703\u6536\u5728\u9019\u88e1\u3002',
        'slugs': ['japanese'],
    },
]


def normalize_subject_key(value):
    return ''.join(str(value or '').strip().lower().split())


def _build_subject_lookup():
    translated_alias_keys = {
        'all': ['subject_all'],
        'chinese': ['subject_chinese', 'subject_chinese_short'],
        'english': ['subject_english', 'subject_english_short'],
        'math': ['subject_math', 'subject_math_short'],
    }
    lookup = {}
    for definition in PRACTICE_SUBJECTS:
        aliases = set(definition.get('aliases', []))
        aliases.add(definition['slug'])
        aliases.add(definition['label'])
        for translation_key in translated_alias_keys.get(definition['slug'], []):
            aliases.add(_t(translation_key, 'zh'))
            aliases.add(_t(translation_key, 'en'))
        for alias in aliases:
            normalized = normalize_subject_key(alias)
            if normalized:
                lookup[normalized] = definition
    return lookup


SUBJECT_LOOKUP = _build_subject_lookup()


def resolve_subject_definition(subject_value):
    normalized = normalize_subject_key(subject_value)
    if not normalized:
        return None
    return SUBJECT_LOOKUP.get(normalized)


def build_subject_catalog():
    from app.models import Question

    questions = Question.query.all()
    counts = {definition['slug']: 0 for definition in PRACTICE_SUBJECTS if definition['slug'] != 'all'}
    extras = {}

    for question in questions:
        subject_label = (question.subject or '').strip()
        definition = resolve_subject_definition(subject_label)
        if definition and definition['slug'] != 'all':
            counts[definition['slug']] += 1
        elif subject_label:
            extras[subject_label] = extras.get(subject_label, 0) + 1

    catalog = []
    total_count = len(questions)
    for definition in PRACTICE_SUBJECTS:
        count = total_count if definition['slug'] == 'all' else counts.get(definition['slug'], 0)
        catalog.append({
            **definition,
            'count': count,
            'available': count > 0,
            'is_custom': False,
            'query_value': definition['slug'],
        })

    for label, count in sorted(extras.items(), key=lambda item: item[0]):
        catalog.append({
            'slug': normalize_subject_key(label) or label,
            'label': label,
            'icon': 'fa-book',
            'aliases': [label],
            'count': count,
            'available': count > 0,
            'is_custom': True,
            'query_value': label,
        })

    return catalog


def _order_subject_cards(cards):
    available_cards = [card for card in cards if card.get('available')]
    unavailable_cards = [card for card in cards if not card.get('available')]
    return available_cards + unavailable_cards


def build_grouped_subject_catalog(subject_cards):
    cards_by_slug = {card['slug']: card for card in subject_cards}
    featured_card = cards_by_slug.get('all')
    used_slugs = {'all'}
    grouped_sections = []

    for group_definition in PRACTICE_SUBJECT_GROUPS:
        cards = []
        for slug in group_definition['slugs']:
            card = cards_by_slug.get(slug)
            if not card:
                continue
            cards.append(card)
            used_slugs.add(slug)

        ordered_cards = _order_subject_cards(cards)
        if not ordered_cards:
            continue

        grouped_sections.append({
            **group_definition,
            'cards': ordered_cards,
            'available_count': sum(1 for card in ordered_cards if card.get('available')),
            'total_count': len(ordered_cards),
        })

    extra_cards = [
        card for card in subject_cards
        if card['slug'] not in used_slugs
    ]
    if extra_cards:
        ordered_extra_cards = _order_subject_cards(sorted(extra_cards, key=lambda card: card['label']))
        other_section = next((section for section in grouped_sections if section['key'] == 'other'), None)
        if other_section:
            merged_cards = _order_subject_cards(other_section['cards'] + ordered_extra_cards)
            other_section['cards'] = merged_cards
            other_section['available_count'] = sum(1 for card in merged_cards if card.get('available'))
            other_section['total_count'] = len(merged_cards)
        else:
            grouped_sections.append({
                'key': 'other',
                'label': '\u5176\u4ed6',
                'description': '\u5176\u4ed6\u5c1a\u672a\u5206\u985e\u7684\u79d1\u76ee\u6703\u96c6\u4e2d\u986f\u793a\u5728\u9019\u88e1\u3002',
                'cards': ordered_extra_cards,
                'available_count': sum(1 for card in ordered_extra_cards if card.get('available')),
                'total_count': len(ordered_extra_cards),
            })

    return featured_card, grouped_sections


def build_practice_question_query(subject_value=None):
    from app.models import Question

    definition = resolve_subject_definition(subject_value)
    query = Question.query

    if definition and definition['slug'] != 'all':
        aliases = sorted({definition['label'], *definition.get('aliases', [])})
        query = query.filter(Question.subject.in_(aliases))
        return definition, query

    if subject_value and normalize_subject_key(subject_value) != 'all':
        fallback_definition = {
            'slug': normalize_subject_key(subject_value) or 'custom',
            'label': subject_value,
            'icon': 'fa-book',
            'aliases': [subject_value],
            'is_custom': True,
        }
        query = query.filter(Question.subject == subject_value)
        return fallback_definition, query

    return resolve_subject_definition('all'), query


def get_question_option_text(question, answer_key):
    options = {
        'A': question.option_a,
        'B': question.option_b,
        'C': question.option_c,
        'D': question.option_d,
    }
    return options.get((answer_key or '').strip().upper(), '')


def apply_attempt_outcome(question, user_answer):
    from app import db
    from app.models import Mistake

    now = datetime.now(timezone.utc)
    answer_key = (user_answer or '').strip().upper()
    is_correct = answer_key == question.correct_answer
    mistake = Mistake.query.filter_by(user_id=current_user.id, question_id=question.id).first()
    resolved_now = False

    if is_correct:
        if mistake:
            current_level = mistake.srs_level or 0
            mistake.last_attempt_date = now
            mistake.srs_level = min(current_level + 1, 7)
            intervals = [0, 1, 2, 4, 7, 14, 30, 60]
            mistake.last_interval = intervals[mistake.srs_level]
            mistake.next_review_date = now + timedelta(days=mistake.last_interval)
            if mistake.srs_level >= 4 and not mistake.is_resolved:
                resolved_now = True
            if mistake.srs_level >= 4:
                mistake.is_resolved = True
    else:
        if mistake:
            mistake.mistake_count = (mistake.mistake_count or 0) + 1
            mistake.srs_level = max((mistake.srs_level or 0) - 1, 0)
            mistake.is_resolved = False
            mistake.last_attempt_date = now
        else:
            mistake = Mistake(user_id=current_user.id, question_id=question.id, last_attempt_date=now)
            db.session.add(mistake)

        mistake.next_review_date = now + timedelta(hours=1)

    return {
        'correct': is_correct,
        'mistake': mistake,
        'resolved_now': resolved_now,
        'answer_key': answer_key,
    }


def reward_correct_progress(correct_count=0, resolved_count=0):
    if correct_count <= 0 and resolved_count <= 0:
        return

    from app import db
    from app.models import GroupMember
    from app.utils.garden_helpers import add_garden_xp

    if correct_count > 0:
        add_garden_xp(5 * correct_count)
    if resolved_count > 0:
        add_garden_xp(20 * resolved_count)

    if correct_count <= 0:
        return

    try:
        memberships = GroupMember.query.filter_by(user_id=current_user.id).all()
        for membership in memberships:
            group = membership.group_info
            group.garden_exp += 10 * correct_count
            next_level_exp = group.garden_level * 1000
            while group.garden_exp >= next_level_exp:
                group.garden_level += 1
                next_level_exp = group.garden_level * 1000
        db.session.commit()
    except Exception:
        db.session.rollback()


def build_exam_feedback(score_percent, wrong_results):
    if score_percent >= 90:
        headline = "\u9019\u6b21\u72c0\u614b\u5f88\u597d\uff0c\u5e7e\u4e4e\u90fd\u638c\u63e1\u4f4f\u4e86\u3002"
    elif score_percent >= 70:
        headline = "\u6574\u9ad4\u4e0d\u932f\uff0c\u5269\u4e0b\u5e7e\u984c\u518d\u88dc\u5f37\u5c31\u6703\u66f4\u7a69\u3002"
    elif score_percent >= 50:
        headline = "\u57fa\u790e\u6709\u8d77\u4f86\uff0c\u4f46\u9084\u6709\u5e7e\u500b\u89c0\u5ff5\u8981\u518d\u91d0\u6e05\u3002"
    else:
        headline = "\u9019\u4efd\u6a21\u8003\u6709\u6293\u5230\u5e7e\u500b\u95dc\u9375\u5f31\u9ede\uff0c\u73fe\u5728\u88dc\u8d77\u4f86\u6700\u6709\u6548\u3002"

    if not wrong_results:
        return headline + " \u63a5\u4e0b\u4f86\u7dad\u6301\u7bc0\u594f\uff0c\u518d\u5237\u4e00\u8f2a\u5c31\u5f88\u597d\u3002"

    weak_subjects = []
    for result in wrong_results:
        subject = result.get('subject')
        if subject and subject not in weak_subjects:
            weak_subjects.append(subject)

    if weak_subjects:
        return headline + f" \u5efa\u8b70\u512a\u5148\u56de\u982d\u8907\u7fd2\uff1a{'\u3001'.join(weak_subjects[:3])}\u3002"
    return headline + " \u5efa\u8b70\u5148\u628a\u932f\u984c\u8a73\u89e3\u770b\u5b8c\uff0c\u518d\u91cd\u65b0\u5237\u4e00\u6b21\u3002"

@study.route("/practice")
@login_required
def practice_hub():
    subject_cards = build_subject_catalog()
    featured_subject_card, grouped_subject_cards = build_grouped_subject_catalog(subject_cards)
    available_subject_count = sum(1 for card in subject_cards if card['slug'] != 'all' and card['available'])
    total_questions = next((card['count'] for card in subject_cards if card['slug'] == 'all'), 0)

    return render_template(
        'practice_hub.html',
        title=_t('nav_practice', current_user.language),
        subject_cards=subject_cards,
        featured_subject_card=featured_subject_card,
        grouped_subject_cards=grouped_subject_cards,
        available_subject_count=available_subject_count,
        total_questions=total_questions,
    )


study.add_url_rule("/practice", endpoint="practice", view_func=practice_hub)

@study.route("/practice/session", methods=['GET', 'POST'])
@login_required
def practice_session():
    from app import db
    from app.models import Question

    if request.method == 'POST':
        question_id = request.form.get('question_id')
        user_answer = request.form.get('answer')
        subject_value = request.form.get('subject') or 'all'

        question = Question.query.get_or_404(question_id)
        result = apply_attempt_outcome(question, user_answer)
        db.session.commit()

        if result['correct']:
            reward_correct_progress(1, 1 if result['resolved_now'] else 0)

        subject_definition = resolve_subject_definition(subject_value)
        next_subject = subject_definition['slug'] if subject_definition else subject_value or 'all'

        return jsonify({
            'correct': result['correct'],
            'correct_answer': question.correct_answer,
            'correct_answer_text': get_question_option_text(question, question.correct_answer),
            'selected_answer': result['answer_key'],
            'selected_answer_text': get_question_option_text(question, result['answer_key']),
            'explanation': question.explanation,
            'srs_level': result['mistake'].srs_level if result['mistake'] else 0,
            'resolved_now': result['resolved_now'],
            'next_question_url': url_for('study.practice_session', subject=next_subject),
        })

    subject_filter = request.args.get('subject')
    question_id = request.args.get('question_id', type=int)
    if not subject_filter and not question_id:
        return redirect(url_for('study.practice_hub'))

    current_subject, query = build_practice_question_query(subject_filter or 'all')
    questions = query.all()
    if not questions:
        flash(_t('msg_no_questions', current_user.language), 'info')
        return redirect(url_for('study.practice_hub'))

    if question_id:
        question = next((item for item in questions if item.id == question_id), None)
        if question is None:
            question = Question.query.get_or_404(question_id)
    else:
        question = random.choice(questions)

    active_subject = current_subject or resolve_subject_definition('all')
    current_subject_query = subject_filter or (active_subject['label'] if active_subject.get('is_custom') else active_subject['slug'])

    return render_template(
        'practice_session.html',
        title=_t('nav_practice', current_user.language),
        question=question,
        current_subject=active_subject,
        current_subject_query=current_subject_query,
        question_pool_size=len(questions),
    )

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
    requested_subject = request.args.get('subject', 'math')
    subject_definition = resolve_subject_definition(requested_subject)
    if subject_definition and subject_definition['slug'] != 'all':
        subject = subject_definition['label']
        redirect_subject = subject_definition['slug']
    else:
        subject = request.args.get('subject') or '\u6578\u5b78'
        redirect_subject = normalize_subject_key(subject) or 'all'

    from app.utils.ai_helpers import generate_ai_quiz
    quiz_data = generate_ai_quiz(subject, lang=current_user.language)

    if 'error' in quiz_data:
        return jsonify(quiz_data), 500

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

    return jsonify({
        'status': 'success',
        'question_id': new_q.id,
        'quiz': quiz_data,
        'practice_url': url_for('study.practice_session', subject=redirect_subject, question_id=new_q.id),
    })


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
                    "**模式切換**\n"
                    "| 指令 | 功能 |\n"
                    "|------|------|\n"
                    "| `/antigravity` | 啟動 Antigravity 極效修復模式 |\n"
                    "| `/normal` | 恢復一般溫柔模式 |\n"
                    "| `/coach` | 切換為魔鬼教練模式 |\n"
                    "| `/senior` | 切換為學長模式 |\n\n"
                    "**系統查詢**\n"
                    "| 指令 | 功能 |\n"
                    "|------|------|\n"
                    "| `/status` | 系統狀態總覽 |\n"
                    "| `/users` | 用戶統計與最近註冊列表 |\n"
                    "| `/find 用戶名` | 搜尋特定用戶詳細資訊 |\n"
                    "| `/sessions` | AI 對話統計 |\n"
                    "| `/sysinfo` | 伺服器環境資訊 |\n"
                    "| `/dbcheck` | 資料庫健康檢查 |\n"
                    "| `/logs` | 最近安全日誌 |\n"
                    "| `/keys` | API Key 詳細狀態 |\n\n"
                    "**使用者管理**\n"
                    "| 指令 | 功能 |\n"
                    "|------|------|\n"
                    "| `/ban 用戶名` | 對用戶發出警告/停權 |\n"
                    "| `/unban IP` | 解除 IP 封鎖 |\n"
                    "| `/resetuser 用戶名` | 重設用戶 AI 性格為預設 |\n\n"
                    "**公告與廣播**\n"
                    "| 指令 | 功能 |\n"
                    "|------|------|\n"
                    "| `/broadcast 訊息` | 發布全站廣播 |\n"
                    "| `/announce 訊息` | 建立全站公告 |\n\n"
                    "**工具**\n"
                    "| 指令 | 功能 |\n"
                    "|------|------|\n"
                    "| `/clearkeys` | 清除失效 API Key |\n"
                    "| `/testai 提示詞` | 原始 AI 測試（跳過雪音人格）|\n"
                    "| `/image 描述` | 生成圖片 |\n"
                    "| `/memo 內容` | 新增管理員備忘錄 |\n"
                    "| `/memos` | 查看備忘錄列表 |\n"
                    "| `/clearmemo` | 清除所有備忘錄 |\n"
                    "| `/help` | 顯示此列表 |\n"
                )
                return jsonify({'status': 'success', 'reply': help_text})
            if cmd == '/status':
                from app.models import User, APIKeyTracker
                total_users = User.query.count()
                active_keys = APIKeyTracker.query.filter_by(is_blocked=False).count()
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
                bad = APIKeyTracker.query.filter(APIKeyTracker.is_blocked == True).all()
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

            # ══════════════════════════════════════════════
            # ══  NEW ADMIN COMMANDS (v2.5 Enhancement)  ══
            # ══════════════════════════════════════════════

            # --- /users: 用戶總覽 ---
            if cmd == '/users':
                from app.models import User
                total = User.query.count()
                admins = User.query.filter_by(role='admin').count()
                students = User.query.filter_by(role='student').count()
                guests = User.query.filter_by(role='guest').count()
                recent_users = User.query.order_by(User.id.desc()).limit(5).all()
                recent_list = '\n'.join([f"  • **{u.username}** ({u.email}) — {u.role}" for u in recent_users])
                reply = (
                    f"👥 **用戶總覽**\n\n"
                    f"📊 總用戶數：**{total}**\n"
                    f"👑 管理員：**{admins}**\n"
                    f"📚 學生：**{students}**\n"
                    f"👤 訪客：**{guests}**\n\n"
                    f"🆕 **最近 5 位註冊用戶**\n{recent_list}"
                )
                return jsonify({'status': 'success', 'reply': reply})

            # --- /find 用戶名: 搜尋用戶 ---
            if cmd.startswith('/find '):
                from app.models import User
                query_name = user_msg.strip()[6:].strip()
                if not query_name:
                    return jsonify({'status': 'success', 'reply': '❌ 請輸入用戶名，例如 `/find 小明`'})
                found = User.query.filter(User.username.ilike(f'%{query_name}%')).all()
                if not found:
                    return jsonify({'status': 'success', 'reply': f'🔍 找不到包含「{query_name}」的用戶。'})
                results = []
                for u in found[:10]:
                    last_login_str = (u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else '從未登入')
                    results.append(
                        f"  **{u.username}** (ID: {u.id})\n"
                        f"  📧 {u.email}\n"
                        f"  🏷️ 角色：{u.role} | 🌐 IP：{u.last_ip or '---'}\n"
                        f"  🕐 最後登入：{last_login_str}"
                    )
                reply = f"🔍 **搜尋結果：「{query_name}」** (共 {len(found)} 人)\n\n" + '\n\n'.join(results)
                return jsonify({'status': 'success', 'reply': reply})

            # --- /sessions: AI 對話統計 ---
            if cmd == '/sessions':
                from app.models import ChatSession, ChatMessage
                total_sessions = ChatSession.query.count()
                total_messages = ChatMessage.query.count()
                today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                today_sessions = ChatSession.query.filter(ChatSession.created_at >= today_start).count()
                # Most active user
                from sqlalchemy import func
                top_user_row = db.session.query(
                    ChatSession.user_id, func.count(ChatSession.id).label('cnt')
                ).group_by(ChatSession.user_id).order_by(func.count(ChatSession.id).desc()).first()
                top_user_info = '---'
                if top_user_row:
                    from app.models import User
                    top_u = User.query.get(top_user_row[0])
                    if top_u:
                        top_user_info = f'{top_u.username} ({top_user_row[1]} 次對話)'
                reply = (
                    f"💬 **AI 對話統計**\n\n"
                    f"📊 對話總數：**{total_sessions}**\n"
                    f"✉️ 訊息總數：**{total_messages}**\n"
                    f"📅 今日新增對話：**{today_sessions}**\n"
                    f"🏆 最活躍用戶：**{top_user_info}**"
                )
                return jsonify({'status': 'success', 'reply': reply})

            # --- /ban 用戶名: 停權用戶 ---
            if cmd.startswith('/ban '):
                from app.models import User, IPBan
                target_name = user_msg.strip()[5:].strip()
                if not target_name:
                    return jsonify({'status': 'success', 'reply': '❌ 請輸入用戶名，例如 `/ban 小明`'})
                target = User.query.filter(User.username.ilike(f'%{target_name}%')).first()
                if not target:
                    return jsonify({'status': 'success', 'reply': f'❌ 找不到用戶「{target_name}」'})
                if target.is_admin:
                    return jsonify({'status': 'success', 'reply': '🛡️ 無法對管理員執行停權操作！'})
                if not target.last_ip:
                    return jsonify({'status': 'success', 'reply': f'⚠️ 用戶 **{target.username}** 尚未記錄 IP 位址，無法執行 IP 封鎖。'})
                # Create a 1-day ban
                existing = IPBan.query.filter_by(ip=target.last_ip).first()
                if existing:
                    return jsonify({'status': 'success', 'reply': f'⚠️ IP **{target.last_ip}** 已經在封鎖名單中。'})
                ban = IPBan(
                    ip=target.last_ip,
                    reason=f'管理員透過聊天室指令封鎖 (對象：{target.username})',
                    expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                    is_permanent=False,
                    banned_by_id=current_user.id
                )
                db.session.add(ban)
                db.session.commit()
                reply = (
                    f"🔨 **用戶已停權**\n\n"
                    f"👤 對象：**{target.username}** ({target.email})\n"
                    f"🌐 IP：**{target.last_ip}**\n"
                    f"⏱️ 期限：**1 天**\n"
                    f"📝 原因：管理員聊天室指令\n\n"
                    f"如需更長期限，請至後台「使用者管理」操作。"
                )
                return jsonify({'status': 'success', 'reply': reply})

            # --- /unban IP: 解除封鎖 ---
            if cmd.startswith('/unban '):
                from app.models import IPBan
                target_ip = user_msg.strip()[7:].strip()
                if not target_ip:
                    return jsonify({'status': 'success', 'reply': '❌ 請輸入 IP 位址，例如 `/unban 192.168.1.1`'})
                ban = IPBan.query.filter_by(ip=target_ip).first()
                if not ban:
                    return jsonify({'status': 'success', 'reply': f'🔍 IP **{target_ip}** 不在封鎖名單中。'})
                db.session.delete(ban)
                db.session.commit()
                return jsonify({'status': 'success', 'reply': f'✅ IP **{target_ip}** 已成功解封！'})

            # --- /announce 訊息: 建立公告 ---
            if cmd.startswith('/announce '):
                from app.models import Announcement
                ann_content = user_msg.strip()[10:].strip()
                if not ann_content:
                    return jsonify({'status': 'success', 'reply': '❌ 請輸入公告內容，例如 `/announce 明天停機維護`'})
                ann = Announcement(
                    title='📢 管理員公告',
                    content=ann_content,
                    created_by_id=current_user.id,
                    is_ai_generated=False
                )
                db.session.add(ann)
                db.session.commit()
                reply = (
                    f"📢 **全站公告已建立！**\n\n"
                    f"📝 內容：{ann_content}\n"
                    f"🆔 公告 ID：#{ann.id}\n\n"
                    f"公告會在全站首頁顯示給所有用戶。"
                )
                return jsonify({'status': 'success', 'reply': reply})

            # --- /sysinfo: 系統環境資訊 ---
            if cmd == '/sysinfo':
                import sys
                import platform
                db_uri = db.engine.url
                db_type = 'PostgreSQL' if 'postgresql' in str(db_uri) else ('SQLite' if 'sqlite' in str(db_uri) else str(db_uri.drivername))
                from app.models import APIKeyTracker
                gemini_keys = APIKeyTracker.query.filter_by(provider='gemini').count()
                groq_keys = APIKeyTracker.query.filter_by(provider='groq').count()
                ollama_keys = APIKeyTracker.query.filter_by(provider='ollama').count()
                active_gemini = APIKeyTracker.query.filter_by(provider='gemini', is_blocked=False).count()
                reply = (
                    f"🖥️ **伺服器環境資訊**\n\n"
                    f"🐍 Python 版本：**{sys.version.split()[0]}**\n"
                    f"💻 作業系統：**{platform.system()} {platform.release()}**\n"
                    f"🗄️ 資料庫類型：**{db_type}**\n"
                    f"📦 Flask 版本：**{__import__('flask').__version__}**\n\n"
                    f"🔑 **API Key 健康度**\n"
                    f"  • Gemini：{active_gemini}/{gemini_keys} 可用\n"
                    f"  • Groq：{groq_keys} 組\n"
                    f"  • Ollama：{ollama_keys} 組\n\n"
                    f"🌐 部署平台：**{'Vercel' if os.environ.get('VERCEL') else '本地開發'}**"
                )
                return jsonify({'status': 'success', 'reply': reply})

            # --- /dbcheck: 資料庫健康檢查 ---
            if cmd == '/dbcheck':
                checks = []
                try:
                    result = db.session.execute(text("SELECT 1"))
                    checks.append("✅ 資料庫連線：正常")
                except Exception as e:
                    checks.append(f"❌ 資料庫連線：失敗 ({str(e)[:50]})")
                # Check important tables
                tables_to_check = ['user', 'question', 'chat_session', 'chat_message', 'announcement', 'ip_ban', 'api_key_tracker']
                for table in tables_to_check:
                    try:
                        count = db.session.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
                        checks.append(f"✅ `{table}`：{count} 筆紀錄")
                    except Exception:
                        db.session.rollback()
                        checks.append(f"⚠️ `{table}`：無法存取")
                reply = "🗄️ **資料庫健康檢查**\n\n" + '\n'.join(checks)
                return jsonify({'status': 'success', 'reply': reply})

            # --- /resetuser 用戶名: 重設 AI 性格 ---
            if cmd.startswith('/resetuser '):
                from app.models import User
                target_name = user_msg.strip()[11:].strip()
                if not target_name:
                    return jsonify({'status': 'success', 'reply': '❌ 請輸入用戶名，例如 `/resetuser 小明`'})
                target = User.query.filter(User.username.ilike(f'%{target_name}%')).first()
                if not target:
                    return jsonify({'status': 'success', 'reply': f'❌ 找不到用戶「{target_name}」'})
                old_personality = target.ai_personality
                target.ai_personality = 'ai_personality_gentle'
                db.session.commit()
                reply = (
                    f"🔄 **用戶 AI 性格已重設**\n\n"
                    f"👤 對象：**{target.username}**\n"
                    f"🔙 原性格：{old_personality}\n"
                    f"✨ 新性格：ai_personality_gentle（溫柔型）"
                )
                return jsonify({'status': 'success', 'reply': reply})

            # --- /logs: 安全日誌 ---
            if cmd == '/logs':
                from app.models import IPAccessLog
                try:
                    recent_logs = IPAccessLog.query.order_by(IPAccessLog.timestamp.desc()).limit(10).all()
                    if not recent_logs:
                        return jsonify({'status': 'success', 'reply': '📋 目前沒有安全日誌紀錄。'})
                    log_lines = []
                    for log in recent_logs:
                        tw_time = log.timestamp + timedelta(hours=8)
                        threat_icon = '🔴' if log.threat_level == 'dangerous' else ('🟡' if log.threat_level == 'suspicious' else '🟢')
                        user_name = log.user.username if log.user else '匿名'
                        log_lines.append(f"  {threat_icon} `{tw_time.strftime('%m/%d %H:%M')}` | {log.ip} | {user_name} | {log.path or '/'}")
                    reply = "🛡️ **最近 10 筆安全日誌**\n\n" + '\n'.join(log_lines)
                    return jsonify({'status': 'success', 'reply': reply})
                except Exception as e:
                    db.session.rollback()
                    return jsonify({'status': 'success', 'reply': f'⚠️ 無法讀取安全日誌：{str(e)[:80]}'})

            # --- /keys: API Key 詳細狀態 ---
            if cmd == '/keys':
                from app.models import APIKeyTracker
                all_keys = APIKeyTracker.query.order_by(APIKeyTracker.provider, APIKeyTracker.id).all()
                if not all_keys:
                    return jsonify({'status': 'success', 'reply': '🔑 目前沒有任何 API Key 紀錄。'})
                key_lines = []
                for k in all_keys:
                    status_icon = '🟢' if k.status in ('active', 'standby') and not k.is_blocked else ('🟡' if k.status == 'cooldown' else '🔴')
                    masked = k.api_key[:8] + '...' + k.api_key[-4:] if len(k.api_key) > 12 else k.api_key[:8] + '...'
                    last_used = k.last_used.strftime('%m/%d %H:%M') if k.last_used else '從未使用'
                    key_lines.append(f"  {status_icon} **{k.provider}** | `{masked}` | {k.status} | {last_used}")
                reply = f"🔑 **API Key 狀態一覽** (共 {len(all_keys)} 組)\n\n" + '\n'.join(key_lines)
                return jsonify({'status': 'success', 'reply': reply})

            # --- /testai 提示詞: 原始 AI 測試 ---
            if cmd.startswith('/testai '):
                raw_prompt = user_msg.strip()[8:].strip()
                if not raw_prompt:
                    return jsonify({'status': 'success', 'reply': '❌ 請輸入測試提示詞，例如 `/testai 你好`'})
                try:
                    from app.utils.ai_helpers import generate_text_with_fallback
                    raw_reply = generate_text_with_fallback(raw_prompt, system_instruction='You are a helpful AI assistant. Respond concisely.', user=current_user)
                    reply = (
                        f"🧪 **原始 AI 測試回應**\n\n"
                        f"📤 **Prompt：**\n{raw_prompt}\n\n"
                        f"📥 **回應：**\n{raw_reply}"
                    )
                    return jsonify({'status': 'success', 'reply': reply})
                except Exception as e:
                    return jsonify({'status': 'success', 'reply': f'❌ AI 測試失敗：{str(e)[:100]}'})

            # --- /image 描述: 生成圖片 ---
            if cmd.startswith('/image '):
                img_prompt = user_msg.strip()[7:].strip()
                if not img_prompt:
                    return jsonify({'status': 'success', 'reply': '❌ 請輸入圖片描述，例如 `/image 一隻可愛的貓咪在讀書`'})
                reply = f"🎨 **圖片生成中...**\n\n[DRAW: {img_prompt}]"
                return jsonify({'status': 'success', 'reply': reply})

            # --- /memo 內容: 新增備忘錄 ---
            if cmd.startswith('/memo '):
                from app.models import MemoryFragment
                memo_content = user_msg.strip()[6:].strip()
                if not memo_content:
                    return jsonify({'status': 'success', 'reply': '❌ 請輸入備忘錄內容，例如 `/memo 記得更新 SSL 憑證`'})
                fragment = MemoryFragment(
                    user_id=current_user.id,
                    category='admin_memo',
                    content=memo_content,
                    importance=5
                )
                db.session.add(fragment)
                db.session.commit()
                return jsonify({'status': 'success', 'reply': f'📝 **備忘錄已儲存！**\n\n內容：{memo_content}\n🆔 ID：#{fragment.id}'})

            # --- /memos: 查看備忘錄 ---
            if cmd == '/memos':
                from app.models import MemoryFragment
                memos = MemoryFragment.query.filter_by(
                    user_id=current_user.id, category='admin_memo'
                ).order_by(MemoryFragment.created_at.desc()).limit(20).all()
                if not memos:
                    return jsonify({'status': 'success', 'reply': '📋 目前沒有備忘錄。使用 `/memo 內容` 新增一則。'})
                memo_lines = []
                for m in memos:
                    tw_time = m.created_at + timedelta(hours=8)
                    memo_lines.append(f"  • `#{m.id}` {tw_time.strftime('%m/%d %H:%M')} — {m.content}")
                reply = f"📋 **管理員備忘錄** (共 {len(memos)} 則)\n\n" + '\n'.join(memo_lines)
                return jsonify({'status': 'success', 'reply': reply})

            # --- /clearmemo: 清除備忘錄 ---
            if cmd == '/clearmemo':
                from app.models import MemoryFragment
                count = MemoryFragment.query.filter_by(
                    user_id=current_user.id, category='admin_memo'
                ).delete()
                db.session.commit()
                return jsonify({'status': 'success', 'reply': f'🗑️ **已清除 {count} 則備忘錄**'})

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
        # Flask return ensures only one response per request. Double response likely browser-side retry.
        return jsonify({'reply': _t('msg_ai_offline', current_user.language).format(error=str(e)), 'error': str(e)}), 200

@study.route("/api/chat/sessions")
@login_required
def get_chat_sessions():
    from app.models import ChatSession
    from sqlalchemy.exc import ProgrammingError, OperationalError
    from app import db
    from sqlalchemy import text
    
    try:
        sessions = ChatSession.query.filter_by(user_id=current_user.id).order_by(
            ChatSession.is_pinned.desc(), 
            ChatSession.created_at.desc()
        ).all()
        return jsonify([{
            'id': s.id, 
            'title': s.title, 
            'created_at': s.created_at.isoformat(),
            'is_pinned': s.is_pinned
        } for s in sessions])
    except (ProgrammingError, OperationalError):
        db.session.rollback()
        # Fallback to auto-migrate 'is_pinned' column (fixes Vercel DB sync issue)
        try:
            # Try SQLite/PostgreSQL syntax for adding column safely
            db.session.execute(text("ALTER TABLE chat_session ADD COLUMN is_pinned BOOLEAN DEFAULT FALSE;"))
            db.session.commit()
        except:
            db.session.rollback()
            
        sessions = ChatSession.query.filter_by(user_id=current_user.id).order_by(
            ChatSession.created_at.desc()
        ).all()
        return jsonify([{
            'id': s.id, 
            'title': s.title, 
            'created_at': s.created_at.isoformat(),
            'is_pinned': getattr(s, 'is_pinned', False)
        } for s in sessions])

@study.route("/api/chat/session/<int:session_id>", methods=['DELETE'])
@login_required
def delete_chat_session(session_id):
    from app import db
    from app.models import ChatSession
    session = ChatSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return jsonify({'error': _t('msg_unauthorized', current_user.language)}), 403
    
    db.session.delete(session)
    db.session.commit()
    return jsonify({'success': True, 'message': 'Session deleted successfully'})

@study.route("/api/chat/session/<int:session_id>/pin", methods=['PATCH'])
@login_required
def pin_chat_session(session_id):
    from app import db
    from app.models import ChatSession
    session = ChatSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return jsonify({'error': _t('msg_unauthorized', current_user.language)}), 403
    
    session.is_pinned = not session.is_pinned
    db.session.commit()
    return jsonify({'success': True, 'is_pinned': session.is_pinned})

@study.route("/api/chat/session/<int:session_id>/rename", methods=['PATCH'])
@login_required
def rename_chat_session(session_id):
    from app import db
    from app.models import ChatSession
    session = ChatSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return jsonify({'error': _t('msg_unauthorized', current_user.language)}), 403
    
    data = request.get_json()
    new_title = data.get('title')
    if not new_title or not new_title.strip():
        return jsonify({'error': 'Title cannot be empty'}), 400
        
    session.title = new_title.strip()[:100]  # Max length 100
    db.session.commit()
    return jsonify({'success': True, 'title': session.title})


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

@study.route("/generate_exam", methods=['GET', 'POST'])
@login_required
def generate_exam():
    from app import db
    from app.models import Mistake

    mistakes = Mistake.query.filter_by(user_id=current_user.id, is_resolved=False).order_by(Mistake.mistake_count.desc()).limit(5).all()

    if request.method == 'POST':
        if not mistakes:
            return jsonify({'status': 'empty', 'message': _t('msg_no_mistakes', current_user.language)}), 400

        payload = request.get_json(silent=True) or {}
        answers = payload.get('answers') or {}
        results = []
        correct_count = 0
        resolved_count = 0

        for index, mistake in enumerate(mistakes, start=1):
            question = mistake.question
            if not question:
                continue

            user_answer = (answers.get(str(question.id)) or '').strip().upper()
            evaluation = apply_attempt_outcome(question, user_answer)
            if evaluation['correct']:
                correct_count += 1
            if evaluation['resolved_now']:
                resolved_count += 1

            results.append({
                'index': index,
                'question_id': question.id,
                'subject': question.subject,
                'content_text': question.content_text,
                'selected_answer': evaluation['answer_key'] or '\u672a\u4f5c\u7b54',
                'selected_answer_text': get_question_option_text(question, evaluation['answer_key']) or '\u9019\u984c\u672a\u4f5c\u7b54',
                'correct_answer': question.correct_answer,
                'correct_answer_text': get_question_option_text(question, question.correct_answer),
                'is_correct': evaluation['correct'],
                'explanation': question.explanation or '\u9019\u984c\u76ee\u524d\u6c92\u6709\u984c\u76ee\u89e3\u6790\uff0c\u5efa\u8b70\u5148\u56de\u982d\u8907\u7fd2\u984c\u5e79\u95dc\u9375\u5b57\u8207\u6b63\u78ba\u9078\u9805\u3002',
            })

        db.session.commit()
        reward_correct_progress(correct_count, resolved_count)

        total_questions = len(results)
        score_percent = round((correct_count / total_questions) * 100) if total_questions else 0
        wrong_results = [item for item in results if not item['is_correct']]

        return jsonify({
            'status': 'success',
            'score_percent': score_percent,
            'correct_count': correct_count,
            'wrong_count': total_questions - correct_count,
            'total_questions': total_questions,
            'feedback': build_exam_feedback(score_percent, wrong_results),
            'results': results,
        })

    if not mistakes:
        flash(_t('msg_no_mistakes', current_user.language), "info")
        return redirect(url_for('study.practice_hub'))

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


