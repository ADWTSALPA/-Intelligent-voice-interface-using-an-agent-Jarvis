"""
voice.py
--------
Layer φωνής για τον JARVIS.

Αναλαμβάνει:
- Τον recognizer και το microphone object
- Text-to-speech μέσω edge-tts
- Ασφαλές queue ώστε δύο φωνές να μην ακούγονται μαζί
- Άμεση διακοπή της φωνής μέσω pygame.mixer

Η αναπαραγωγή ήχου γίνεται με το pygame.mixer, ώστε η ομιλία να μπορεί
να διακοπεί ακαριαία (pygame.mixer.music.stop()) όταν δοθεί η εντολή
"jarvis stop".
"""

import os
import asyncio
import threading
import queue
import tempfile
import time

import speech_recognition as sr
import edge_tts
import pygame

# Import ολόκληρου του config module ώστε να διαβάζουμε τη ζωντανή τιμή
# του VOICE_ENABLED κάθε φορά (το ui.py την αλλάζει με το mute toggle).
from . import config
from .config import VOICE, RATE, PITCH, state, signals, add_log


# ---------------------------------------------------------------------------
# Αντικείμενα αναγνώρισης φωνής
# ---------------------------------------------------------------------------

# Δημιουργούνται μία φορά κατά το import. Ο recognizer κρατάει tuning
# (π.χ. energy_threshold) — δεν θέλουμε καινούριο instance σε κάθε κλήση.
recognizer = sr.Recognizer()
mic = sr.Microphone()

try:
    # Ακούμε το δωμάτιο για 2 δευτερόλεπτα ώστε να καταλάβει ο recognizer
    # τι σημαίνει "σιωπή" στο περιβάλλον σου.
    with mic as source:
        recognizer.adjust_for_ambient_noise(source, duration=2)
        # Floor 300 — μερικές φορές το adjust_for_ambient_noise βάζει πολύ
        # χαμηλό threshold σε ήσυχα δωμάτια και πιάνει την αναπνοή.
        recognizer.energy_threshold = max(recognizer.energy_threshold, 300)
except Exception as e:
    print("Microphone setup error:", e)


# ---------------------------------------------------------------------------
# Αρχικοποίηση pygame mixer
#
# Το καλούμε μία φορά κατά το import. Αν αποτύχει (π.χ. δεν υπάρχει
# audio device), το πιάνουμε ώστε να μη σκάσει όλη η εφαρμογή.
# ---------------------------------------------------------------------------

_mixer_ready = False
try:
    pygame.mixer.init()
    _mixer_ready = True
except Exception as e:
    print("pygame mixer init error:", e)


# ---------------------------------------------------------------------------
# Κατάσταση του voice queue
# ---------------------------------------------------------------------------

_voice_queue = queue.Queue()
_voice_worker_started = False
_stop_speaking = threading.Event()


# ---------------------------------------------------------------------------
# TTS βοηθητικά
# ---------------------------------------------------------------------------

async def _create_tts_file(text, filename):
    """Καλεί το edge-tts (που είναι async) και αποθηκεύει το mp3."""
    communicate = edge_tts.Communicate(
        text,
        voice=VOICE,
        rate=RATE,
        pitch=PITCH
    )
    await communicate.save(filename)


def _clear_voice_queue():
    """Καθαρίζει όλα τα μηνύματα φωνής που περιμένουν στην ουρά."""
    try:
        while True:
            _voice_queue.get_nowait()
            _voice_queue.task_done()
    except queue.Empty:
        pass


def _play_file_interruptible(mp3_path):
    """
    Παίζει ένα mp3 με το pygame, αλλά ΧΩΡΙΣ να μπλοκάρει εντελώς.

    Αντί να περιμένουμε «τυφλά» να τελειώσει ο ήχος, μπαίνουμε σε ένα
    μικρό loop που ελέγχει κάθε 50ms:
      - αν τελείωσε φυσιολογικά ο ήχος  → βγαίνουμε
      - αν πατήθηκε το _stop_speaking   → ΚΟΒΟΥΜΕ τον ήχο αμέσως

    Αυτό είναι το κλειδί ώστε το "jarvis stop" να δουλεύει στην πράξη.
    """
    if not _mixer_ready:
        # Fallback: αν για κάποιο λόγο δεν ξεκίνησε ο mixer, τουλάχιστον
        # μην κρασάρουμε — απλώς δεν παίζει ήχος.
        print("[voice] pygame mixer δεν είναι έτοιμος — παράλειψη ήχου.")
        return

    try:
        pygame.mixer.music.load(mp3_path)
        pygame.mixer.music.play()
    except Exception as e:
        print("Voice playback error:", e)
        return

    # Loop ελέγχου: όσο παίζει ο ήχος ΚΑΙ δεν ζητήθηκε stop
    while pygame.mixer.music.get_busy():
        if _stop_speaking.is_set():
            # Άμεση διακοπή του ήχου που παίζει αυτή τη στιγμή
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            break
        time.sleep(0.05)

    # Σιγουρευόμαστε ότι το αρχείο δεν είναι πια "κλειδωμένο" από τον mixer
    # ώστε να μπορεί να σβηστεί παρακάτω (σημαντικό στα Windows).
    try:
        pygame.mixer.music.unload()
    except Exception:
        pass


def stop_speaking():
    """
    Σταματάει τη μελλοντική ομιλία ΚΑΙ διακόπτει την τρέχουσα ΑΜΕΣΩΣ.

    Με το pygame πλέον η διακοπή είναι πραγματική:
    - σηκώνουμε το _stop_speaking flag (το play loop θα το δει σε <50ms)
    - καλούμε και απευθείας pygame.mixer.music.stop() για ακαριαία κοπή
    - καθαρίζουμε την ουρά ώστε να μην ξεκινήσει επόμενο μήνυμα
    """
    _stop_speaking.set()

    # Άμεση κοπή του ήχου που παίζει αυτή τη στιγμή
    if _mixer_ready:
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass

    _clear_voice_queue()

    state.set(is_speaking=False)
    signals.voice_active.emit(False)


def wait_until_silent(timeout=10.0):
    """
    Περιμένει μέχρι να ολοκληρωθεί όλη η αναπαραγωγή ομιλίας.

    Χρησιμοποιείται πριν το κλείσιμο της εφαρμογής, ώστε ο χρήστης
    να ακούσει ολόκληρο το "JARVIS standing down" πριν τερματιστεί
    η διεργασία.

    Η συνάρτηση περιμένει μέχρι:
    - η ουρά μηνυμάτων (_voice_queue) να αδειάσει, ΚΑΙ
    - το is_speaking flag να γίνει False

    Έχει timeout ασφαλείας για την περίπτωση που το edge-tts κολλήσει.
    """
    deadline = time.time() + timeout

    # Μικρή αναμονή ώστε ο worker να προλάβει να σηκώσει το επόμενο
    # μήνυμα από την ουρά (το speak_async επιστρέφει άμεσα).
    time.sleep(0.15)

    while time.time() < deadline:
        queue_empty = _voice_queue.empty()
        speaking = state.get("is_speaking")

        # Έτοιμοι όταν δεν υπάρχει pending μήνυμα και δεν παίζει κάτι.
        if queue_empty and not speaking:
            # Μικρό grace period για το πραγματικό τέλος του ήχου.
            time.sleep(0.2)
            return

        time.sleep(0.1)

    # Timeout — προχωράμε ούτως ή άλλως ώστε να μην κρεμάσει η εφαρμογή.
    print("[voice] wait_until_silent: timeout — προχωράω στο κλείσιμο.")


def _voice_worker():
    """
    Background worker που παίζει τα μηνύματα φωνής ένα-ένα.
    Έτσι αποφεύγεται το να μιλάνε δύο φωνές ταυτόχρονα.
    """
    while True:
        text = _voice_queue.get()

        try:
            if not text:
                continue

            if _stop_speaking.is_set():
                continue

            state.set(is_speaking=True)
            signals.voice_active.emit(True)

            # Μοναδικό tempfile για κάθε φωνή ώστε παράλληλες κλήσεις
            # να μην αλληλεπικαλύπτονται.
            mp3_path = tempfile.mktemp(suffix=".mp3", prefix="jarvis_")

            try:
                asyncio.run(_create_tts_file(text, mp3_path))

                if not _stop_speaking.is_set():
                    _play_file_interruptible(mp3_path)

            except Exception as e:
                if not _stop_speaking.is_set():
                    print("Voice error:", e)

            finally:
                state.set(is_speaking=False)
                signals.voice_active.emit(False)

                # Καθαρίζουμε πάντα το αρχείο για να μη γεμίζει το temp folder.
                try:
                    os.remove(mp3_path)
                except Exception:
                    pass

        finally:
            _voice_queue.task_done()


def _start_voice_worker():
    """Ξεκινάει τον worker μία και μοναδική φορά (lazy init)."""
    global _voice_worker_started

    if _voice_worker_started:
        return

    _voice_worker_started = True
    thread = threading.Thread(target=_voice_worker, daemon=True)
    thread.start()


# ---------------------------------------------------------------------------
# Δημόσιο API
# ---------------------------------------------------------------------------

def speak(text):
    """
    Μιλάει αμέσως, μπλοκάροντας το τρέχον thread.
    Χρησιμοποιείται όταν χρειαζόμαστε σειριακή συμπεριφορά — π.χ.
    ο JARVIS λέει "Yes, sir?" ΠΡΙΝ ακούσει την επόμενη εντολή.

    ΣΗΜΕΙΩΣΗ: Παρότι "μπλοκάρει", το play loop ελέγχει το stop flag,
    οπότε ακόμα κι αυτή η συνάρτηση μπορεί να διακοπεί από stop_speaking().
    """
    if not text:
        return

    add_log(f"JARVIS: {text}")

    if not config.VOICE_ENABLED:
        return

    # Καθαρίζουμε το stop flag ώστε μια ρητή κλήση speak() (π.χ. το
    # "Yes, sir?" μετά το wake word) να παίξει κανονικά, ακόμα κι αν
    # προηγουμένως είχε δοθεί εντολή "jarvis stop".
    _stop_speaking.clear()

    state.set(is_speaking=True)
    signals.voice_active.emit(True)

    # Μοναδικό tempfile για να μην επικαλυφθεί με άλλη ομιλία
    mp3_path = tempfile.mktemp(suffix=".mp3", prefix="jarvis_")

    try:
        asyncio.run(_create_tts_file(text, mp3_path))

        if not _stop_speaking.is_set():
            _play_file_interruptible(mp3_path)

    except Exception as e:
        if not _stop_speaking.is_set():
            print("Voice error:", e)

    finally:
        state.set(is_speaking=False)
        signals.voice_active.emit(False)

        try:
            os.remove(mp3_path)
        except Exception:
            pass


def speak_async(text):
    """
    Προσθέτει τη φωνή στην ουρά.
    Πολλαπλές κλήσεις θα ακουστούν η μία μετά την άλλη — όχι μαζί.
    """
    if not text:
        return

    add_log(f"JARVIS: {text}")

    if not config.VOICE_ENABLED:
        return

    _start_voice_worker()

    # Μια καινούρια κανονική ομιλία πρέπει να επαναφέρει το stop flag,
    # αλλιώς ο χρήστης δεν θα ακούει τίποτα μετά από ένα προηγούμενο "stop".
    _stop_speaking.clear()

    _voice_queue.put(text)