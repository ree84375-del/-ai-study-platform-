from app.models import User, ChatMessage, GroupMessage, ChatSession
from app.utils.ai_helpers import generate_text_with_fallback
import json

def get_ban_recommendation(user_id):
    """
    Analyzes user behavior and returns a recommended ban duration and reason.
    """
    user = User.query.get(user_id)
    if not user:
        return {"error": "User not found"}
        
    # Gather context: Recent 20 group messages and 20 private AI chat messages
    group_msgs = GroupMessage.query.filter_by(user_id=user_id).order_by(GroupMessage.created_at.desc()).limit(20).all()
    
    # For private chat, we need sessions first
    private_msgs = []
    sessions = ChatSession.query.filter_by(user_id=user_id).order_by(ChatSession.created_at.desc()).limit(5).all()
    for s in sessions:
        msgs = ChatMessage.query.filter_by(session_id=s.id, role='user').order_by(ChatMessage.created_at.desc()).limit(10).all()
        private_msgs.extend(msgs)
    
    # Sort and format context
    all_context = []
    for m in group_msgs:
        all_context.append(f"[群組訊息] {m.content}")
    for m in private_msgs:
        all_context.append(f"[私聊訊息] {m.content}")
        
    context_text = "\n".join(all_context[-30:]) # Last 30 combined
    
    if not context_text:
        return {
            "recommendation": "警告", 
            "days": 0, 
            "reason": "目前尚無明顯違規紀錄，建議先以警告為主。",
            "analysis": "系統未發現該用戶有任何發言紀錄。"
        }

    prompt = f"""
你是「雪音」AI 學習平台的安全監督助理。請分析以下用戶的發言行為，並給出停權建議。

用戶名稱：{user.username}
近期發言內容：
{context_text}

請判斷其嚴重程度（由輕到重）：
1. 警告 (Warning) - 輕微騷擾、刷屏、非惡意垃圾訊息。
2. 停權 1, 3, 5, 7, 14, 30 天 - 惡意辱罵、色情、仇恨言論、持續干擾他人。
3. 永久凍結 (Permanent) - 極度嚴重違規、駭客行為、大量發布違法資訊、累犯。

請以 JSON 格式回傳，包含以下欄位：
- recommendation: 建議類型 (警告, 1天, 3天, 5天, 7天, 14天, 30天, 永久凍結)
- days: 具體天數 (Int, 永久為 -1, 警告為 0)
- reason: 給管理員的專業理由 (繁體中文)
- analysis: 具體分析內容 (繁體中文)

只回傳 JSON，不要有其他描述。
"""

    try:
        response_text = generate_text_with_fallback(prompt, system_instruction="你是一個客觀公正的安全監督專家。").strip()
        
        # Clean up possible markdown code blocks
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
            
        data = json.loads(response_text)
        return data
    except Exception as e:
        return {
            "error": str(e),
            "recommendation": "警告",
            "days": 0,
            "reason": "AI 分析發生錯誤，請管理員手動判斷。",
            "analysis": f"錯誤訊息: {str(e)}"
        }
