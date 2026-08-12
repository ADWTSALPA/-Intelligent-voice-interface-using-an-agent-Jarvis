"""
config.py
---------
Κεντρικές ρυθμίσεις και κοινή κατάσταση για τον JARVIS.

Περιέχει:
- Σταθερές της εφαρμογής
- Αρχικοποίηση του OpenAI client
- Κοινή runtime κατάσταση (state)
- Qt signals
- Βοηθητικές συναρτήσεις για log/status (ασφαλείς για threads)
"""

import os
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from PySide6.QtCore import QObject, Signal

# Το OpenAI είναι προαιρετικό — αν δεν είναι εγκατεστημένο, χρησιμοποιούμε
# τον offline parser. Το try/except επιτρέπει στην εφαρμογή να τρέξει έτσι κι αλλιώς.
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


# ---------------------------------------------------------------------------
# Περιβάλλον / API
# ---------------------------------------------------------------------------

# Το override=True κάνει την τιμή του .env να υπερισχύει έναντι παλιών
# τιμών που μπορεί να υπάρχουν στο περιβάλλον του λειτουργικού.
load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = "gpt-4.1-mini"

# Δημιουργούμε τον client μόνο αν υπάρχει το SDK ΚΑΙ το key.
client = OpenAI(api_key=OPENAI_API_KEY) if OpenAI and OPENAI_API_KEY else None


# ---------------------------------------------------------------------------
# Αρχεία
# ---------------------------------------------------------------------------

CACHE_FILE = "app_cache.json"  # Θυμάται τα paths που έχουν βρεθεί


# ---------------------------------------------------------------------------
# Ρυθμίσεις φωνής / αναγνώρισης
# ---------------------------------------------------------------------------

# Εσωτερική σταθερά για το TTS. Παραμένει True μόνιμα στην τρέχουσα έκδοση,
# αφού πια δεν υπάρχει κουμπί Mute Voice στο UI (αντικαταστάθηκε από Mute Mic).
# Διατηρείται για ενδεχόμενη μελλοντική επαναφορά της λειτουργίας.
VOICE_ENABLED = True

WAKE_WORDS = ["jarvis"]

# Φράσεις που σημαίνουν "σταμάτα να μιλάς".
# Τις κρατάμε εδώ ώστε να μην επαναλαμβάνονται σε διαφορετικά αρχεία.
STOP_PHRASES = [
    "stop",
    "be quiet",
    "shut up",
    "stop speaking",
    "silence",
]

RECOGNITION_LANGUAGE = "en-US"

# Ρυθμίσεις φωνής για το edge-tts
VOICE = "en-GB-RyanNeural"   # Βρετανική ανδρική φωνή
RATE = "-12%"                # Λίγο πιο αργά
PITCH = "-5Hz"               # Λίγο πιο μπάσα


# ---------------------------------------------------------------------------
# Runtime κατάσταση
# ---------------------------------------------------------------------------

@dataclass
class AppState:
    """
    Μικρό κοινόχρηστο αντικείμενο κατάστασης.

    Αντικαθιστά τα σκόρπια global variables σε όλα τα modules.

    Πεδία:
    - assistant_running: True όταν ο JARVIS είναι ενεργοποιημένος (μετά το Start)
    - processing:       True όταν επεξεργάζεται μία εντολή ή περιμένει απάντηση
    - is_speaking:      True όταν παίζει TTS audio
    - stop_listening:   callable που σταματάει το background listener
                        (το επιστρέφει το recognizer.listen_in_background)
    - mic_muted:        True όταν το μικρόφωνο είναι muted μέσω του UI κουμπιού.
                        Όταν είναι True, ο background listener δεν τρέχει.
    - extra:            dictionary για τυχόν επιπλέον τιμές runtime
    """
    assistant_running: bool = False
    processing: bool = False
    is_speaking: bool = False
    stop_listening: Any = None
    mic_muted: bool = False          # ← ΝΕΟ: κατάσταση mic mute toggle

    # Επιπλέον dictionary για τιμές που δεν έχουν προκαθορισμένο πεδίο
    extra: dict = field(default_factory=dict)

    def get(self, key: str, default=None):
        return getattr(self, key, self.extra.get(key, default))

    def set(self, **kwargs):
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
            else:
                self.extra[key] = value


# Ένα μοναδικό instance — όλα τα modules κάνουν import το ίδιο `state`.
state = AppState()


# ---------------------------------------------------------------------------
# Qt signals
#
# Τα background threads ΔΕΝ μπορούν να αγγίξουν Qt widgets άμεσα (θα
# κάνει crash). Αντί γι' αυτό κάνουν emit ένα signal, και το slot τρέχει
# στο main thread όπου είναι ασφαλές.
# ---------------------------------------------------------------------------

class UISignals(QObject):
    log = Signal(str)            # Προσθήκη γραμμής στο UI log
    status = Signal(str)         # Ενημέρωση του status label
    voice_active = Signal(bool)  # Ξεκίνημα/τέλος του palpitating animation
    request_exit = Signal()      # Ζητάμε καθαρό κλείσιμο από worker thread


signals = UISignals()


# ---------------------------------------------------------------------------
# Βοηθητικές συναρτήσεις (ασφαλείς για threads)
# ---------------------------------------------------------------------------

def add_log(text: str):
    """
    Τυπώνει στο terminal ΚΑΙ στέλνει στο UI log.
    Ασφαλής να καλεστεί από worker threads — τα Qt signals είναι thread-safe.
    """
    print(text)
    signals.log.emit(str(text))


def set_status(text: str):
    """Ενημερώνει το status label του UI."""
    signals.status.emit(str(text))