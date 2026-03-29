from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash
from flask_login import login_required, current_user
import random
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_
from app.utils.i18n import get_text as _t
from app.utils.question_bank_metadata import detect_booklet_label, extract_question_hierarchy

study = Blueprint('study', __name__)

PRACTICE_MODE_PREVIEW = 'preview'
PRACTICE_MODE_PRACTICE = 'practice'
PRACTICE_BANK_LABEL = '一般國中練習'

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
    {
        'slug': 'all',
        'label': '全部',
        'icon': 'fa-layer-group',
        'aliases': ['all', '全部'],
        'family': 'all',
        'hub_visible': False,
    },
    {
        'slug': 'chinese',
        'label': '國文',
        'icon': 'fa-book-open',
        'aliases': ['國文', '中文', 'Chinese', 'subject_chinese', 'subject_chinese_short'],
        'family': 'core',
        'hub_visible': True,
    },
    {
        'slug': 'english',
        'label': '英文',
        'icon': 'fa-language',
        'aliases': ['英文', 'English', 'subject_english', 'subject_english_short'],
        'family': 'core',
        'hub_visible': True,
    },
    {
        'slug': 'math',
        'label': '數學',
        'icon': 'fa-calculator',
        'aliases': ['數學', 'Math', 'subject_math', 'subject_math_short'],
        'family': 'core',
        'hub_visible': True,
    },
    {
        'slug': 'geography',
        'label': '地理',
        'icon': 'fa-map-location-dot',
        'aliases': ['地理', 'Geography'],
        'family': 'social',
        'hub_visible': True,
    },
    {
        'slug': 'history',
        'label': '歷史',
        'icon': 'fa-landmark',
        'aliases': ['歷史', 'History'],
        'family': 'social',
        'hub_visible': True,
    },
    {
        'slug': 'civics',
        'label': '公民',
        'icon': 'fa-scale-balanced',
        'aliases': ['公民', 'Civics'],
        'family': 'social',
        'hub_visible': True,
    },
    {
        'slug': 'biology',
        'label': '生物',
        'icon': 'fa-dna',
        'aliases': ['生物', 'Biology'],
        'family': 'nature',
        'hub_visible': True,
    },
    {
        'slug': 'integrated_science',
        'label': '理化',
        'icon': 'fa-flask-vial',
        'aliases': ['理化', 'Integrated Science'],
        'family': 'nature',
        'hub_visible': True,
    },
    {
        'slug': 'earth_science',
        'label': '地科',
        'icon': 'fa-earth-asia',
        'aliases': ['地科', 'Earth Science'],
        'family': 'nature',
        'hub_visible': True,
    },
]

PRACTICE_REVIEW_CENTER_CARDS = [
    {
        'slug': 'chinese',
        'kind': 'subject',
        'label': '國文',
        'icon': 'fa-book-open',
        'description': '把國中國文題庫整理成可直接預覽、可直接練習的完整入口。',
        'accent': 'rose',
    },
    {
        'slug': 'english',
        'kind': 'subject',
        'label': '英文',
        'icon': 'fa-language',
        'description': '閱讀、字彙、文法與對話都會進同一套國中英文複習流程。',
        'accent': 'blue',
    },
    {
        'slug': 'math',
        'kind': 'subject',
        'label': '數學',
        'icon': 'fa-calculator',
        'description': '保留冊別、主章節與細主題，先不打亂，方便從單元慢慢補強。',
        'accent': 'gold',
    },
    {
        'slug': 'social',
        'kind': 'group',
        'label': '社會',
        'icon': 'fa-landmark-flag',
        'description': '社會不再混成一包，已拆成地理、歷史、公民三條主線。',
        'children': ['geography', 'history', 'civics'],
        'accent': 'teal',
    },
    {
        'slug': 'nature',
        'kind': 'group',
        'label': '自然',
        'icon': 'fa-seedling',
        'description': '自然已拆成生物、理化、地科，後面可以直接選分科刷主題。',
        'children': ['biology', 'integrated_science', 'earth_science'],
        'accent': 'green',
    },
]

PRACTICE_BRANCH_SECTIONS = [
    {
        'slug': 'social',
        'label': '社會分科',
        'icon': 'fa-diagram-project',
        'description': '先挑地理、歷史或公民，再進預覽模式或練習模式。',
        'children': ['geography', 'history', 'civics'],
    },
    {
        'slug': 'nature',
        'label': '自然分科',
        'icon': 'fa-compass-drafting',
        'description': '先挑生物、理化或地科，每一科都保留冊別、主章節與細主題。',
        'children': ['biology', 'integrated_science', 'earth_science'],
    },
]

PRACTICE_EXAM_DEFAULTS = {
    'chinese': {
        'count': 42,
        'duration': 70,
        'official_range': '國文科 38～46 題 / 70 分鐘',
        'preset_label': '會考國文預設',
    },
    'english': {
        'count': 43,
        'duration': 60,
        'official_range': '英語閱讀 40～45 題 / 60 分鐘',
        'preset_label': '會考英文預設',
    },
    'math': {
        'count': 25,
        'duration': 80,
        'official_range': '數學科 23～28 題 / 80 分鐘',
        'preset_label': '會考數學預設',
    },
    'geography': {
        'count': 54,
        'duration': 70,
        'official_range': '參考社會科 50～60 題 / 70 分鐘',
        'preset_label': '社會科練習預設',
    },
    'history': {
        'count': 54,
        'duration': 70,
        'official_range': '參考社會科 50～60 題 / 70 分鐘',
        'preset_label': '社會科練習預設',
    },
    'civics': {
        'count': 54,
        'duration': 70,
        'official_range': '參考社會科 50～60 題 / 70 分鐘',
        'preset_label': '社會科練習預設',
    },
    'biology': {
        'count': 50,
        'duration': 70,
        'official_range': '參考自然科 45～55 題 / 70 分鐘',
        'preset_label': '自然科練習預設',
    },
    'integrated_science': {
        'count': 50,
        'duration': 70,
        'official_range': '參考自然科 45～55 題 / 70 分鐘',
        'preset_label': '自然科練習預設',
    },
    'earth_science': {
        'count': 50,
        'duration': 70,
        'official_range': '參考自然科 45～55 題 / 70 分鐘',
        'preset_label': '自然科練習預設',
    },
}

PRACTICE_COUNT_CHOICES = [5, 10, 25, 40, 42, 43, 50, 54]
PRACTICE_DURATION_CHOICES = [5, 10, 30, 50, 60, 70, 80, 100]

PRACTICE_SCOPE_ALL = 'all'
PRACTICE_CHAPTER_ALL = 'all'
PRACTICE_TOPIC_ALL = 'all'
PRACTICE_BOOKLETS = [
    {'query_value': PRACTICE_SCOPE_ALL, 'label': '總複習', 'short_label': '總複習', 'description': '先不分冊，保留目前題庫順序做整科瀏覽或整科練習。'},
    {'query_value': '第一冊', 'label': '第一冊', 'short_label': '一冊', 'description': '保留第一冊題庫順序，只做第一冊。'},
    {'query_value': '第二冊', 'label': '第二冊', 'short_label': '二冊', 'description': '保留第二冊題庫順序，只做第二冊。'},
    {'query_value': '第三冊', 'label': '第三冊', 'short_label': '三冊', 'description': '保留第三冊題庫順序，只做第三冊。'},
    {'query_value': '第四冊', 'label': '第四冊', 'short_label': '四冊', 'description': '保留第四冊題庫順序，只做第四冊。'},
    {'query_value': '第五冊', 'label': '第五冊', 'short_label': '五冊', 'description': '保留第五冊題庫順序，只做第五冊。'},
    {'query_value': '第六冊', 'label': '第六冊', 'short_label': '六冊', 'description': '保留第六冊題庫順序，只做第六冊。'},
]


def normalize_scope_filter(value, default=PRACTICE_SCOPE_ALL):
    normalized = normalize_subject_key(value)
    if not normalized or normalized == 'all':
        return default
    return str(value or '').strip()


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


def normalize_booklet_filter(value):
    normalized = normalize_subject_key(value)
    if not normalized or normalized in {'all', 'allbooks', 'total', 'review', '總複習'}:
        return PRACTICE_SCOPE_ALL
    for booklet in PRACTICE_BOOKLETS:
        if normalize_subject_key(booklet['query_value']) == normalized:
            return booklet['query_value']
    return PRACTICE_SCOPE_ALL


def build_booklet_scope_options(base_query, selected_booklet=PRACTICE_SCOPE_ALL):
    from app.models import Question

    rows = base_query.with_entities(Question.category, Question.tags).all()
    counts = {booklet['query_value']: 0 for booklet in PRACTICE_BOOKLETS[1:]}
    total_count = len(rows)

    for category_value, tags_value in rows:
        detected = detect_booklet_label(category_value or '', tags_value or '')
        if detected:
            counts[detected] += 1

    options = []
    selected_booklet = normalize_booklet_filter(selected_booklet)
    for booklet in PRACTICE_BOOKLETS:
        query_value = booklet['query_value']
        count = total_count if query_value == PRACTICE_SCOPE_ALL else counts.get(query_value, 0)
        options.append({
            **booklet,
            'count': count,
            'available': count > 0,
            'is_selected': selected_booklet == query_value,
        })

    return options


def resolve_selected_booklet(booklet_options, requested_booklet):
    normalized = normalize_booklet_filter(requested_booklet)
    selected = next((item for item in booklet_options if item['query_value'] == normalized and item['available']), None)
    if selected:
        return selected
    return next((item for item in booklet_options if item['query_value'] == PRACTICE_SCOPE_ALL), booklet_options[0])


def build_named_scope_options(values, selected_value, all_label, all_description, icon):
    selected_value = normalize_scope_filter(selected_value)
    total_count = sum(values.values())
    options = [{
        'query_value': PRACTICE_SCOPE_ALL,
        'label': all_label,
        'description': all_description,
        'icon': icon,
        'count': total_count,
        'available': total_count > 0,
        'is_selected': selected_value == PRACTICE_SCOPE_ALL,
    }]

    for label, count in values.items():
        options.append({
            'query_value': label,
            'label': label,
            'description': f'只看 {label} 這個範圍的題目。',
            'icon': icon,
            'count': count,
            'available': count > 0,
            'is_selected': selected_value == label,
        })

    return options


def resolve_selected_scope(scope_options, requested_value):
    normalized = normalize_scope_filter(requested_value)
    selected = next((item for item in scope_options if item['query_value'] == normalized and item['available']), None)
    if selected:
        return selected
    return next((item for item in scope_options if item['query_value'] == PRACTICE_SCOPE_ALL), scope_options[0])


def build_chapter_scope_options(base_query, selected_chapter=PRACTICE_CHAPTER_ALL):
    from app.models import Question

    rows = base_query.order_by(Question.id.asc()).with_entities(Question.category, Question.tags).all()
    counts = {}
    for category_value, tags_value in rows:
        hierarchy = extract_question_hierarchy(category_value or '', tags_value or '')
        chapter = hierarchy['chapter']
        if chapter:
            counts[chapter] = counts.get(chapter, 0) + 1

    return build_named_scope_options(
        counts,
        selected_chapter,
        all_label='全部主章節',
        all_description='保留目前科目與冊別，先看所有主章節。',
        icon='fa-folder-tree',
    )


def build_topic_scope_options(base_query, selected_topic=PRACTICE_TOPIC_ALL):
    from app.models import Question

    rows = base_query.order_by(Question.id.asc()).with_entities(Question.category, Question.tags).all()
    counts = {}
    for category_value, tags_value in rows:
        hierarchy = extract_question_hierarchy(category_value or '', tags_value or '')
        topic = hierarchy['topic']
        if topic:
            counts[topic] = counts.get(topic, 0) + 1

    return build_named_scope_options(
        counts,
        selected_topic,
        all_label='全部細主題',
        all_description='保留目前科目、冊別與主章節，先看所有細主題。',
        icon='fa-bookmark',
    )


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


def build_review_center_catalog(subject_cards):
    cards_by_slug = {card['slug']: card for card in subject_cards}
    review_center_cards = []

    for card_definition in PRACTICE_REVIEW_CENTER_CARDS:
        if card_definition['kind'] == 'subject':
            source_card = cards_by_slug.get(card_definition['slug'])
            if not source_card:
                continue
            review_center_cards.append({
                **card_definition,
                'count': source_card['count'],
                'available': source_card['available'],
                'href': url_for('study.practice_session', subject=source_card['query_value']),
            })
            continue

        child_cards = [
            cards_by_slug[child_slug]
            for child_slug in card_definition.get('children', [])
            if child_slug in cards_by_slug
        ]
        count = sum(card['count'] for card in child_cards)
        review_center_cards.append({
            **card_definition,
            'count': count,
            'available': any(card['available'] for card in child_cards),
            'child_labels': [card['label'] for card in child_cards],
            'href': f"#branch-{card_definition['slug']}",
        })

    branch_sections = []
    for section_definition in PRACTICE_BRANCH_SECTIONS:
        child_cards = [
            cards_by_slug[child_slug]
            for child_slug in section_definition.get('children', [])
            if child_slug in cards_by_slug
        ]
        ordered_cards = _order_subject_cards(child_cards)
        if not ordered_cards:
            continue
        branch_sections.append({
            **section_definition,
            'cards': ordered_cards,
            'available_count': sum(1 for card in ordered_cards if card.get('available')),
            'question_count': sum(card['count'] for card in ordered_cards),
        })

    return review_center_cards, branch_sections


def get_practice_defaults(subject_definition):
    defaults = PRACTICE_EXAM_DEFAULTS.get((subject_definition or {}).get('slug'), {
        'count': 10,
        'duration': 30,
        'official_range': '一般練習 10 題 / 30 分鐘',
        'preset_label': '一般練習預設',
    })
    return {
        **defaults,
        'count_choices': PRACTICE_COUNT_CHOICES,
        'duration_choices': PRACTICE_DURATION_CHOICES,
    }


def build_practice_count_options(question_pool_size, default_count):
    normalized_pool_size = max(int(question_pool_size or 0), 0)
    available_choices = [choice for choice in PRACTICE_COUNT_CHOICES if choice <= normalized_pool_size]
    if normalized_pool_size and normalized_pool_size not in available_choices:
        available_choices.append(normalized_pool_size)

    options = []
    for choice in available_choices:
        if choice == normalized_pool_size and choice not in PRACTICE_COUNT_CHOICES:
            label = f'全部 {choice} 題'
        else:
            label = f'{choice} 題'
        options.append({
            'value': choice,
            'label': label,
            'is_recommended': choice == min(default_count, normalized_pool_size) if normalized_pool_size else False,
        })
    return options


def build_practice_duration_options(default_duration):
    return [
        {
            'value': choice,
            'label': f'{choice} 分鐘',
            'is_recommended': choice == default_duration,
        }
        for choice in PRACTICE_DURATION_CHOICES
    ]


def resolve_practice_choice(requested_value, options, default_value):
    option_values = [option['value'] for option in options]
    if requested_value in option_values:
        return requested_value
    if default_value in option_values:
        return default_value
    return option_values[-1] if option_values else 0


def build_local_practice_explanation(question):
    explanation = (question.explanation or '').strip()
    if explanation:
        return explanation

    hierarchy = extract_question_hierarchy(question.category or '', question.tags or '', question.subject or '')
    correct_answer = (question.correct_answer or '').strip().upper() or 'A'
    correct_answer_text = get_question_option_text(question, correct_answer)
    hints = [f'正確答案是 {correct_answer}。']

    if correct_answer_text:
        hints.append(f'對應的選項內容是「{correct_answer_text}」。')
    if hierarchy['topic']:
        hints.append(f'這題屬於「{hierarchy["topic"]}」主題，先回頭抓題幹中的關鍵字，再對照正確選項。')
    elif hierarchy['chapter']:
        hints.append(f'這題屬於「{hierarchy["chapter"]}」章節，建議先把本章節核心概念再對一次。')
    else:
        hints.append('建議先圈出題幹關鍵字，再逐一排除不符合條件的選項。')

    hints.append('如果是觀念題，先確認定義與條件；如果是計算題，先列出已知條件再代入。')
    return ' '.join(hints)


def build_practice_question_query(
    subject_value=None,
    booklet_value=PRACTICE_SCOPE_ALL,
    chapter_value=PRACTICE_CHAPTER_ALL,
    topic_value=PRACTICE_TOPIC_ALL,
):
    from app.models import Question

    definition = resolve_subject_definition(subject_value)
    query = Question.query

    if definition and definition['slug'] != 'all':
        aliases = sorted({definition['label'], *definition.get('aliases', [])})
        query = query.filter(Question.subject.in_(aliases))
    elif subject_value and normalize_subject_key(subject_value) != 'all':
        fallback_definition = build_custom_subject_definition(subject_value)
        query = query.filter(Question.subject == subject_value)
        definition = fallback_definition

    else:
        definition = resolve_subject_definition('all')

    booklet_value = normalize_booklet_filter(booklet_value)
    if booklet_value != PRACTICE_SCOPE_ALL:
        query = query.filter(
            or_(
                Question.category.contains(booklet_value),
                Question.tags.contains(booklet_value),
            )
        )

    chapter_value = normalize_scope_filter(chapter_value, default=PRACTICE_CHAPTER_ALL)
    if chapter_value != PRACTICE_SCOPE_ALL:
        query = query.filter(
            or_(
                Question.category.contains(chapter_value),
                Question.tags.contains(chapter_value),
            )
        )

    topic_value = normalize_scope_filter(topic_value, default=PRACTICE_TOPIC_ALL)
    if topic_value != PRACTICE_SCOPE_ALL:
        query = query.filter(
            or_(
                Question.tags.contains(topic_value),
                Question.category.contains(topic_value),
            )
        )

    return definition, query


def build_custom_subject_definition(subject_value):
    return {
        'slug': normalize_subject_key(subject_value) or 'custom',
        'label': subject_value,
        'icon': 'fa-book',
        'aliases': [subject_value],
        'is_custom': True,
    }


def normalize_practice_mode(value):
    normalized = normalize_subject_key(value)
    if normalized in {'practice', 'drill', 'train', 'training', '練習', '練習模式'}:
        return PRACTICE_MODE_PRACTICE
    return PRACTICE_MODE_PREVIEW


def get_practice_mode_meta(mode):
    if mode == PRACTICE_MODE_PRACTICE:
        return {
            'label': '練習模式',
            'icon': 'fa-dumbbell',
            'hero_title': '整份作答到最後一題，再一次交卷批改。',
            'hero_description': '這個模式會載入該科全部題目。你可以上一題、下一題、隨時改答案，最後按交卷後才一次算成績、顯示答案和詳解。',
            'result_label': '100 分制交卷',
            'question_prompt': '先完成這一整份練習卷。你可以自由切換題目和修改答案，最後一題按交卷才會批改。',
        }

    return {
        'label': '預覽模式',
        'icon': 'fa-eye',
        'hero_title': '直接看這一科的全部題目，點開就看答案和詳解。',
        'hero_description': '這個模式適合先瀏覽題庫與解析。每一題都可以單獨展開，直接查看正確答案與詳解，不會進入考試流程。',
        'result_label': '點題即看詳解',
        'question_prompt': '預覽模式會把該科全部題目排好，點開任一題就能立即看答案和詳解。',
    }


def build_practice_question_item(question, index):
    hierarchy = extract_question_hierarchy(question.category or '', question.tags or '', question.subject or '')
    options = []
    for key, text in [('A', question.option_a), ('B', question.option_b), ('C', question.option_c), ('D', question.option_d)]:
        if text:
            options.append({
                'key': key,
                'text': text,
                'is_correct': key == question.correct_answer,
            })

    return {
        'index': index,
        'id': question.id,
        'subject': question.subject,
        'booklet': hierarchy['booklet'],
        'chapter': hierarchy['chapter'],
        'topic': hierarchy['topic'],
        'category': question.category or '',
        'content_text': question.content_text,
        'options': options,
        'correct_answer': question.correct_answer,
        'correct_answer_text': get_question_option_text(question, question.correct_answer),
        'explanation': build_local_practice_explanation(question),
    }


def build_practice_submission_results(questions, submitted_answers):
    results = []
    correct_count = 0
    resolved_count = 0

    for index, question in enumerate(questions, start=1):
        user_answer = (submitted_answers.get(str(question.id)) or submitted_answers.get(question.id) or '').strip().upper()
        hierarchy = extract_question_hierarchy(question.category or '', question.tags or '', question.subject or '')

        if user_answer:
            evaluation = apply_attempt_outcome(question, user_answer)
        else:
            evaluation = {
                'correct': False,
                'resolved_now': False,
                'answer_key': '',
            }

        if evaluation['correct']:
            correct_count += 1
        if evaluation['resolved_now']:
            resolved_count += 1

        results.append({
            'index': index,
            'question_id': question.id,
            'subject': question.subject,
            'booklet': hierarchy['booklet'],
            'chapter': hierarchy['chapter'],
            'topic': hierarchy['topic'],
            'category': question.category or '',
            'content_text': question.content_text,
            'selected_answer': evaluation['answer_key'] or '未作答',
            'selected_answer_text': get_question_option_text(question, evaluation['answer_key']) or '這題未作答',
            'correct_answer': question.correct_answer,
            'correct_answer_text': get_question_option_text(question, question.correct_answer),
            'is_correct': evaluation['correct'],
            'explanation': build_local_practice_explanation(question),
            'options': build_practice_question_item(question, index)['options'],
        })

    return {
        'results': results,
        'correct_count': correct_count,
        'resolved_count': resolved_count,
    }


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

def parse_question_id_list(raw_value):
    question_ids = []
    seen = set()
    for chunk in str(raw_value or '').split(','):
        chunk = chunk.strip()
        if not chunk.isdigit():
            continue
        question_id = int(chunk)
        if question_id in seen:
            continue
        seen.add(question_id)
        question_ids.append(question_id)
    return question_ids


def build_selected_question_set(questions, selected_count):
    if selected_count <= 0:
        return []
    return questions[:selected_count]


@study.route("/practice")
@login_required
def practice_hub():
    subject_cards = build_subject_catalog()
    review_center_cards, branch_sections = build_review_center_catalog(subject_cards)
    available_subject_count = sum(
        1
        for card in subject_cards
        if card['slug'] != 'all' and card.get('hub_visible', True) and card['available']
    )
    total_questions = sum(
        card['count']
        for card in subject_cards
        if card['slug'] != 'all' and not card.get('is_custom')
    )

    return render_template(
        'practice_hub.html',
        title=_t('nav_practice', current_user.language),
        practice_bank_label=PRACTICE_BANK_LABEL,
        subject_cards=subject_cards,
        review_center_cards=review_center_cards,
        branch_sections=branch_sections,
        available_subject_count=available_subject_count,
        total_questions=total_questions,
    )


study.add_url_rule("/practice", endpoint="practice", view_func=practice_hub)

@study.route("/practice/session")
@login_required
def practice_session():
    from app.models import Question

    subject_filter = request.args.get('subject')
    question_id = request.args.get('question_id', type=int)
    requested_mode = (request.args.get('mode') or '').strip()
    requested_booklet = request.args.get('booklet')
    requested_chapter = request.args.get('chapter')
    requested_topic = request.args.get('topic')
    requested_count = request.args.get('count', type=int)
    requested_duration = request.args.get('duration', type=int)
    start_requested = normalize_subject_key(request.args.get('start')) in {'1', 'true', 'yes', 'start'}
    practice_mode = normalize_practice_mode(requested_mode) if requested_mode else None

    if not subject_filter and not question_id:
        return redirect(url_for('study.practice_hub'))

    subject_seed = subject_filter or 'all'
    normalized_subject_seed = normalize_subject_key(subject_seed)
    if normalized_subject_seed in {'social', 'nature'}:
        return redirect(url_for('study.practice_hub') + f'#branch-{normalized_subject_seed}')

    if question_id and not subject_filter:
        focused_question = Question.query.get_or_404(question_id)
        subject_seed = focused_question.subject or 'all'

    current_subject, subject_query = build_practice_question_query(subject_seed)
    booklet_options = build_booklet_scope_options(subject_query, selected_booklet=requested_booklet)
    selected_booklet = resolve_selected_booklet(booklet_options, requested_booklet)
    current_subject, booklet_query = build_practice_question_query(subject_seed, booklet_value=selected_booklet['query_value'])
    chapter_options = build_chapter_scope_options(booklet_query, selected_chapter=requested_chapter)
    selected_chapter = resolve_selected_scope(chapter_options, requested_chapter)
    current_subject, chapter_query = build_practice_question_query(
        subject_seed,
        booklet_value=selected_booklet['query_value'],
        chapter_value=selected_chapter['query_value'],
    )
    topic_options = build_topic_scope_options(chapter_query, selected_topic=requested_topic)
    selected_topic = resolve_selected_scope(topic_options, requested_topic)
    current_subject, query = build_practice_question_query(
        subject_seed,
        booklet_value=selected_booklet['query_value'],
        chapter_value=selected_chapter['query_value'],
        topic_value=selected_topic['query_value'],
    )
    questions = query.order_by(Question.id.asc()).all()
    if not questions:
        flash(_t('msg_no_questions', current_user.language), 'info')
        return redirect(url_for('study.practice_hub'))

    active_subject = current_subject or resolve_subject_definition('all')
    current_subject_query = subject_seed if subject_filter else (active_subject['label'] if active_subject.get('is_custom') else active_subject['slug'])
    question_items = [build_practice_question_item(question, index) for index, question in enumerate(questions, start=1)]
    defaults = get_practice_defaults(active_subject)
    practice_count_options = build_practice_count_options(len(question_items), defaults['count'])
    practice_duration_options = build_practice_duration_options(defaults['duration'])
    selected_count = resolve_practice_choice(requested_count, practice_count_options, defaults['count'])
    selected_duration = resolve_practice_choice(requested_duration, practice_duration_options, defaults['duration'])

    if not requested_mode:
        return render_template(
            'practice_session.html',
            title=_t('nav_practice', current_user.language),
            practice_bank_label=PRACTICE_BANK_LABEL,
            view_state='mode_selector',
            current_subject=active_subject,
            current_subject_query=current_subject_query,
            booklet_options=booklet_options,
            selected_booklet=selected_booklet,
            chapter_options=chapter_options,
            selected_chapter=selected_chapter,
            topic_options=topic_options,
            selected_topic=selected_topic,
            question_pool_size=len(question_items),
            preview_mode_meta=get_practice_mode_meta(PRACTICE_MODE_PREVIEW),
            practice_mode_meta=get_practice_mode_meta(PRACTICE_MODE_PRACTICE),
            practice_defaults=defaults,
        )

    practice_mode_meta = get_practice_mode_meta(practice_mode)

    if practice_mode == PRACTICE_MODE_PREVIEW:
        return render_template(
            'practice_preview.html',
            title=_t('nav_practice', current_user.language),
            practice_bank_label=PRACTICE_BANK_LABEL,
            question_items=question_items,
            current_subject=active_subject,
            current_subject_query=current_subject_query,
            booklet_options=booklet_options,
            selected_booklet=selected_booklet,
            chapter_options=chapter_options,
            selected_chapter=selected_chapter,
            topic_options=topic_options,
            selected_topic=selected_topic,
            question_pool_size=len(question_items),
            practice_mode=practice_mode,
            practice_mode_meta=practice_mode_meta,
        )

    if not start_requested:
        return render_template(
            'practice_session.html',
            title=_t('nav_practice', current_user.language),
            practice_bank_label=PRACTICE_BANK_LABEL,
            view_state='practice_setup',
            current_subject=active_subject,
            current_subject_query=current_subject_query,
            booklet_options=booklet_options,
            selected_booklet=selected_booklet,
            chapter_options=chapter_options,
            selected_chapter=selected_chapter,
            topic_options=topic_options,
            selected_topic=selected_topic,
            question_pool_size=len(question_items),
            practice_mode=practice_mode,
            practice_mode_meta=practice_mode_meta,
            practice_defaults=defaults,
            practice_count_options=practice_count_options,
            practice_duration_options=practice_duration_options,
            selected_count=selected_count,
            selected_duration=selected_duration,
        )

    selected_question_items = build_selected_question_set(question_items, selected_count)
    if not selected_question_items:
        flash(_t('msg_no_questions', current_user.language), 'info')
        return redirect(url_for('study.practice_hub'))

    focus_question_id = question_id if any(item['id'] == question_id for item in selected_question_items) else selected_question_items[0]['id']
    initial_question_index = next((index for index, item in enumerate(selected_question_items) if item['id'] == focus_question_id), 0)

    return render_template(
        'practice_session.html',
        title=_t('nav_practice', current_user.language),
        practice_bank_label=PRACTICE_BANK_LABEL,
        view_state='practice_run',
        question_items=selected_question_items,
        current_subject=active_subject,
        current_subject_query=current_subject_query,
        booklet_options=booklet_options,
        selected_booklet=selected_booklet,
        chapter_options=chapter_options,
        selected_chapter=selected_chapter,
        topic_options=topic_options,
        selected_topic=selected_topic,
        question_pool_size=len(question_items),
        practice_mode=practice_mode,
        practice_mode_meta=practice_mode_meta,
        practice_defaults=defaults,
        practice_count_options=practice_count_options,
        practice_duration_options=practice_duration_options,
        selected_count=selected_count,
        selected_duration=selected_duration,
        selected_question_total=len(selected_question_items),
        selected_question_ids_csv=','.join(str(item['id']) for item in selected_question_items),
        focus_question_id=focus_question_id,
        initial_question_index=initial_question_index,
    )


@study.route("/practice/review", methods=['GET', 'POST'])
@login_required
def practice_review():
    from app import db
    from app.models import Question

    subject_value = request.form.get('subject') or request.args.get('subject') or 'all'
    requested_booklet = request.form.get('booklet') or request.args.get('booklet') or PRACTICE_SCOPE_ALL
    requested_chapter = request.form.get('chapter') or request.args.get('chapter') or PRACTICE_CHAPTER_ALL
    requested_topic = request.form.get('topic') or request.args.get('topic') or PRACTICE_TOPIC_ALL
    requested_count = request.form.get('count', type=int) or request.args.get('count', type=int)
    requested_duration = request.form.get('duration', type=int) or request.args.get('duration', type=int)
    requested_question_ids = parse_question_id_list(request.form.get('question_ids') or request.args.get('question_ids'))
    if request.method == 'GET':
        return redirect(url_for(
            'study.practice_session',
            subject=subject_value,
            booklet=requested_booklet,
            chapter=requested_chapter,
            topic=requested_topic,
            mode=PRACTICE_MODE_PRACTICE,
            count=requested_count,
            duration=requested_duration,
        ))

    current_subject, query = build_practice_question_query(
        subject_value,
        booklet_value=requested_booklet,
        chapter_value=requested_chapter,
        topic_value=requested_topic,
    )
    available_questions = query.order_by(Question.id.asc()).all()
    if not available_questions:
        flash(_t('msg_no_questions', current_user.language), 'info')
        return redirect(url_for('study.practice_hub'))

    active_subject = current_subject or resolve_subject_definition('all')
    defaults = get_practice_defaults(active_subject)
    practice_count_options = build_practice_count_options(len(available_questions), defaults['count'])
    practice_duration_options = build_practice_duration_options(defaults['duration'])
    selected_count = resolve_practice_choice(requested_count, practice_count_options, defaults['count'])
    selected_duration = resolve_practice_choice(requested_duration, practice_duration_options, defaults['duration'])

    if requested_question_ids:
        question_map = {question.id: question for question in available_questions}
        questions = [question_map[question_id] for question_id in requested_question_ids if question_id in question_map]
    else:
        questions = build_selected_question_set(available_questions, selected_count)
    if not questions:
        flash(_t('msg_no_questions', current_user.language), 'info')
        return redirect(url_for('study.practice_hub'))

    submitted_answers = {
        str(question.id): request.form.get(f'answer_{question.id}', '')
        for question in questions
    }
    grading_summary = build_practice_submission_results(questions, submitted_answers)
    db.session.commit()
    reward_correct_progress(grading_summary['correct_count'], grading_summary['resolved_count'])

    current_subject_query = subject_value if request.form.get('subject') else (active_subject['label'] if active_subject.get('is_custom') else active_subject['slug'])
    booklet_options = build_booklet_scope_options(build_practice_question_query(subject_value)[1], selected_booklet=requested_booklet)
    selected_booklet = resolve_selected_booklet(booklet_options, requested_booklet)
    chapter_options = build_chapter_scope_options(
        build_practice_question_query(subject_value, booklet_value=selected_booklet['query_value'])[1],
        selected_chapter=requested_chapter,
    )
    selected_chapter = resolve_selected_scope(chapter_options, requested_chapter)
    topic_options = build_topic_scope_options(
        build_practice_question_query(
            subject_value,
            booklet_value=selected_booklet['query_value'],
            chapter_value=selected_chapter['query_value'],
        )[1],
        selected_topic=requested_topic,
    )
    selected_topic = resolve_selected_scope(topic_options, requested_topic)
    review_items = grading_summary['results']

    total_count = len(review_items)
    correct_count = grading_summary['correct_count']
    wrong_count = total_count - correct_count
    answered_count = sum(1 for value in submitted_answers.values() if str(value or '').strip())
    unanswered_count = total_count - answered_count
    score_percent = round((correct_count / total_count) * 100, 1) if total_count else 0.0
    feedback = build_exam_feedback(score_percent, [item for item in review_items if not item['is_correct']])

    return render_template(
        'practice_review.html',
        title=_t('nav_practice', current_user.language),
        practice_bank_label=PRACTICE_BANK_LABEL,
        current_subject=active_subject,
        current_subject_query=current_subject_query,
        booklet_options=booklet_options,
        selected_booklet=selected_booklet,
        chapter_options=chapter_options,
        selected_chapter=selected_chapter,
        topic_options=topic_options,
        selected_topic=selected_topic,
        review_items=review_items,
        total_count=total_count,
        correct_count=correct_count,
        wrong_count=wrong_count,
        answered_count=answered_count,
        unanswered_count=unanswered_count,
        score_percent=score_percent,
        feedback=feedback,
        practice_defaults=defaults,
        practice_count_options=practice_count_options,
        practice_duration_options=practice_duration_options,
        selected_count=selected_count,
        selected_duration=selected_duration,
        selected_question_ids_csv=','.join(str(question.id) for question in questions),
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
    requested_mode = normalize_practice_mode(request.args.get('mode'))
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
        'practice_url': url_for('study.practice_session', subject=redirect_subject, question_id=new_q.id, mode=requested_mode),
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
    from app.models import ChatSession, ChatMessage
    session = ChatSession.query.get_or_404(session_id)
    if session.user_id != current_user.id:
        return jsonify({'error': _t('msg_unauthorized', current_user.language)}), 403

    messages = ChatMessage.query.filter_by(session_id=session.id).order_by(
        ChatMessage.created_at.asc(),
        ChatMessage.id.asc(),
    ).all()

    payload = [{
        'role': message.role,
        'content': message.content,
        'created_at': message.created_at.isoformat() if message.created_at else None,
    } for message in messages]
    return jsonify({'messages': payload})

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


