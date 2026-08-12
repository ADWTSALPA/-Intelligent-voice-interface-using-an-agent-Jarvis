"""
cache.py
--------
Μικρό JSON cache.

Το χρησιμοποιεί το finder.py για να θυμάται τα paths που έχουν βρεθεί,
ώστε ο JARVIS να μη σκανάρει το filesystem κάθε φορά.
"""

import os
import json

from .config import CACHE_FILE, add_log
from .voice import speak_async


def load_cache():
    """
    Φορτώνει το cache από τον δίσκο.
    Επιστρέφει άδειο dict αν το αρχείο δεν υπάρχει ή είναι κατεστραμμένο.
    """
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            # Κατεστραμμένο JSON — κάνουμε σαν να ήταν άδειο, αντί να κράσει.
            return {}

    return {}


def save_cache(cache):
    """Αποθηκεύει το cache στον δίσκο. Σιωπηλό αν αποτύχει."""
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=4, ensure_ascii=False)
    except Exception as e:
        add_log(f"Cache save error: {e}")


def reset_cache():
    """
    Σβήνει το cache file.
    Καλείται από το κουμπί "Reset Cache" του UI.
    Χρήσιμο όταν μια εφαρμογή έχει μετακινηθεί και τα cached paths
    δείχνουν σε λάθος μέρος.
    """
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
            add_log("Cache cleared.")
            speak_async("Cache has been reset, sir.")
        except Exception as e:
            add_log(f"Cache reset error: {e}")
            speak_async("I could not reset the cache, sir.")
    else:
        add_log("Cache already empty.")
        speak_async("Cache is already empty, sir.")
