import redis
import json
import hashlib

# Connexion Redis
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# Durée de cache par type de donnée
TTL = {
    "politician":    60 * 60 * 24,      # 24h — données générales
    "condamnations": 60 * 60 * 6,       # 6h  — condamnations (Playwright coûteux)
    "votes":         60 * 60 * 12,      # 12h — votes
    "propositions":  60 * 60 * 12,      # 12h — propositions de loi
    "news":          60 * 60 * 2,       # 2h  — actualités (changent plus vite)
}

def _key(name: str, type: str = "politician") -> str:
    """Génère une clé Redis unique et normalisée."""
    clean = name.lower().strip()
    hash  = hashlib.md5(clean.encode()).hexdigest()[:8]
    return f"politico:{type}:{clean.replace(' ', '_')}:{hash}"

def get_cache(name: str, type: str = "politician") -> dict:
    """Récupère un résultat depuis le cache Redis."""
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
    """Stocke un résultat dans le cache Redis."""
    try:
        key = _key(name, type)
        ttl = TTL.get(type, 60 * 60 * 24)
        r.setex(key, ttl, json.dumps(data, ensure_ascii=False))
        print(f"[CACHE SET] {key} — TTL {ttl}s")
    except Exception as e:
        print(f"[CACHE ERROR] {e}")

def invalidate_cache(name: str) -> None:
    """Supprime toutes les entrées cache pour un nom."""
    try:
        pattern = f"politico:*:{name.lower().strip().replace(' ', '_')}:*"
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
            print(f"[CACHE INVALIDATED] {len(keys)} clés supprimées")
    except Exception as e:
        print(f"[CACHE ERROR] {e}")

def cache_stats() -> dict:
    """Retourne des stats sur le cache."""
    try:
        keys = r.keys("politico:*")
        return {
            "total_entrees": len(keys),
            "entrees":       keys[:20],
        }
    except Exception as e:
        return {"erreur": str(e)}
