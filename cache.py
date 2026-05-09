import redis
import json
import hashlib
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
r = redis.from_url(REDIS_URL, decode_responses=True)

TTL = {
    "politician":    60 * 60 * 24,
    "condamnations": 60 * 60 * 6,
    "votes":         60 * 60 * 12,
    "propositions":  60 * 60 * 12,
    "news":          60 * 60 * 2,
}

def _key(name: str, type: str = "politician") -> str:
    clean = name.lower().strip()
    hash  = hashlib.md5(clean.encode()).hexdigest()[:8]
    return f"politico:{type}:{clean.replace(' ', '_')}:{hash}"

def get_cache(name: str, type: str = "politician") -> dict:
    try:
        key  = _key(name, type)
        data = r.get(key)
        if data:
            print(f"[CACHE HIT] {key}")
            return json.loads(data)
        print(f"[CACHE MISS] {key}")
        return None
    except Exception as e:
        print(f"[CACHE ERROR] {e}")
        return None

def set_cache(name: str, data: dict, type: str = "politician") -> None:
    try:
        key = _key(name, type)
        ttl = TTL.get(type, 60 * 60 * 24)
        r.setex(key, ttl, json.dumps(data, ensure_ascii=False))
        print(f"[CACHE SET] {key} — TTL {ttl}s")
    except Exception as e:
        print(f"[CACHE ERROR] {e}")

def invalidate_cache(name: str) -> None:
    try:
        pattern = f"politico:*:{name.lower().strip().replace(' ', '_')}:*"
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
    except Exception as e:
        print(f"[CACHE ERROR] {e}")

def cache_stats() -> dict:
    try:
        keys = r.keys("politico:*")
        return {
            "total_entrees": len(keys),
            "entrees":       keys[:20],
        }
    except Exception as e:
        return {"erreur": str(e)}
