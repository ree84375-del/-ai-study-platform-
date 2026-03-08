from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SelectField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, NumberRange

class UpdateProfileForm(FlaskForm):
    bio = TextAreaField('自我介紹/座右銘', validators=[Length(max=200)])
    learning_goals = TextAreaField('當前學習目標', validators=[DataRequired(), Length(max=300)])
    ai_personality = SelectField('AI 教師性格', choices=[
        ('gentle', '溫柔體貼 (雪音)'),
        ('strict', '嚴厲冷酷 (影狼)'),
        ('humorous', '幽默風趣 (大黑天)'),
        ('logical', '冷靜理性 (青龍)')
    ])
    preferred_theme = SelectField('網站介面主題', choices=[
        ('default', '經典和風'),
        ('sakura', '漫天櫻花'),
        ('moonlight', '玄月幽螢'),
        ('shrine', '神宮祈願')
    ])
    pomodoro_duration = IntegerField('番茄鐘時長 (分鐘)', validators=[NumberRange(min=5, max=60)], default=25)
    submit = SubmitField('保存修改')
