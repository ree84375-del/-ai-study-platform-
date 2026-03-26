import os
import google.generativeai as genai
from app.utils.ai_helpers import get_gemini_keys, get_usable_keys, mark_key_status

def get_embedding(text, model="models/text-embedding-004"):
    """
    Generates a semantic embedding vector for the given text using Gemini.
    Default model is text-embedding-004 (768 dimensions).
    """
    if not text:
        return None
    
    # Sanitization: Gemini embeddings have limits on input length
    text = text[:10000] # Safe limit for most embedding models
    
    keys = get_usable_keys('gemini', get_gemini_keys())
    errors = []
    
    for key in keys:
        try:
            genai.configure(api_key=key)
            # Embedding task
            result = genai.embed_content(
                model=model,
                content=text,
                task_type="retrieval_document",
                title="Memory Fragment"
            )
            
            if 'embedding' in result:
                mark_key_status('gemini', key, 'standby')
                return result['embedding']
                
        except Exception as e:
            err_str = str(e)
            errors.append(err_str)
            mark_key_status('gemini', key, 'error', err_str)
            
    # If all fail, return None (calling function should handle this)
    return None

def get_query_embedding(text, model="models/text-embedding-004"):
    """
    Generates an embedding optimized for retrieval queries.
    """
    if not text:
        return None
        
    keys = get_usable_keys('gemini', get_gemini_keys())
    
    for key in keys:
        try:
            genai.configure(api_key=key)
            result = genai.embed_content(
                model=model,
                content=text,
                task_type="retrieval_query"
            )
            if 'embedding' in result:
                mark_key_status('gemini', key, 'standby')
                return result['embedding']
        except Exception as e:
            mark_key_status('gemini', key, 'error', str(e))
            
    return None
