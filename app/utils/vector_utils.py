from app import db
from sqlalchemy import text

def save_user_memory(user_id, content, category='general', importance=1):
    """
    Embeds content and saves it to VectorMemory.
    """
    from app.models import VectorMemory
    from app.utils.embeddings import get_embedding
    import logging
    try:
        vector = get_embedding(content)
        if not vector:
            logging.error(f"Failed to generate embedding for memory: {content[:50]}")
            return False
            
        memory = VectorMemory(
            user_id=user_id,
            content=content,
            embedding=vector,
            metadata_json={'category': category, 'importance': importance}
        )
        db.session.add(memory)
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logging.error(f"Error saving vector memory: {e}")
        return False

def search_relevant_memories(user_id, query, limit=5):
    """
    Searches for the most relevant memories for a user given a query.
    Uses cosine distance for semantic similarity.
    """
    from app.models import VectorMemory
    from app.utils.embeddings import get_query_embedding
    import logging
    try:
        query_vector = get_query_embedding(query)
        if not query_vector:
            return []
            
        # Semantic search using pgvector
        # Note: We use cosine_distance for similarity (smaller is more similar)
        # .limit(limit) ensures we only get the top matches
        results = VectorMemory.query.filter_by(user_id=user_id).order_by(
            VectorMemory.embedding.cosine_distance(query_vector)
        ).limit(limit).all()
        
        return results
    except Exception as e:
        logging.error(f"Error searching vector memory: {e}")
        return []

def migrate_legacy_memories(user_id=None):
    """
    Migrates existing MemoryFragment entries into VectorMemory.
    If user_id is provided, only migrates for that user.
    """
    from app.models import MemoryFragment
    query = MemoryFragment.query
    if user_id:
        query = query.filter_by(user_id=user_id)
        
    fragments = query.all()
    count = 0
    for f in fragments:
        # Check if already migrated (optional optimization)
        success = save_user_memory(f.user_id, f.content, f.category, f.importance)
        if success:
            count += 1
            
    return count

def ensure_pgvector_extension():
    """
    Attempts to enable the vector extension in PostgreSQL.
    """
    import logging
    try:
        db.session.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logging.error(f"Failed to enable pgvector extension: {e}")
        return False
