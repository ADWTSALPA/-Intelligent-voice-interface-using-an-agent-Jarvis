"""
executor.py
-----------
Το layer που "κάνει τα πράγματα" — μετατρέπει τα parsed intents σε
πραγματικές ενέργειες: άνοιγμα app, αναζήτηση, ώρα κ.λπ.

Περιέχει επίσης το wake-word callback που ενεργοποιείται κάθε φορά
που ο recognizer ακούει φωνή, και τη νέα toggle_microphone() που
σταματάει/ξεκινάει τον background listener.
"""

import time
import datetime
import random

import speech_recognition as sr

from .config import (
    state, signals, set_status, add_log,
    WAKE_WORDS, RECOGNITION_LANGUAGE, STOP_PHRASES,
)
from .voice import speak, speak_async, stop_speaking, recognizer, mic, wait_until_silent
from .finder import (
    find_path, launch_path, close_app,
    open_google_search, open_youtube_search,
)
from .brain import agent_brain, clean_command, answer_general_question


def say(text, silent=False):
    """
    Μιλάει μόνο όταν silent=False.
    Έτσι τα multi-action steps δεν "πατάει" το ένα την απάντηση του άλλου.
    """
    if not silent and text:
        speak_async(text)


def listen_for_followup(prompt, phrase_time_limit=8):
    """
    Κάνει μια ερώτηση συμπληρωματική και ακούει την απάντηση χωρίς να
    χρειάζεται ξανά το wake word.
    """
    speak(prompt)
    time.sleep(0.3)

    try:
        with sr.Microphone() as source:
            audio = recognizer.listen(source, phrase_time_limit=phrase_time_limit)

        followup = recognizer.recognize_google(
            audio,
            language=RECOGNITION_LANGUAGE
        ).lower()

        add_log(f"FOLLOW-UP HEARD: {followup}")
        return followup.strip()

    except Exception:
        # Αποτυχία αναγνώρισης (σιωπή, θόρυβος, network) — απλώς γυρνάμε άδειο
        return ""


def is_incomplete_question(text):
    """
    Εντοπίζει ημιτελείς ερωτήσεις, π.χ.:
    - tell me about
    - explain
    - who is
    - what is
    """
    text = text.lower().strip()

    incomplete_questions = [
        "",
        "tell me about",
        "tell me about.",
        "explain",
        "explain.",
        "who is",
        "who is.",
        "what is",
        "what is.",
        "tell me",
        "tell me.",
    ]

    return text in incomplete_questions


def build_followup_question(original_target, followup):
    """
    Φτιάχνει μια πλήρη ερώτηση συνδυάζοντας την αρχική ημιτελή
    και το follow-up του χρήστη.
    """
    original_target = original_target.lower().strip()
    followup = followup.strip()

    if original_target.startswith("who is"):
        return f"Who is {followup}"

    if original_target.startswith("what is"):
        return f"What is {followup}"

    if original_target.startswith("explain"):
        return f"Explain {followup}"

    return f"Tell me about {followup}"


def perform_intent(intent):
    """
    Dispatch με βάση το intent['action'].

    Επιστρέφει False ΜΟΝΟ όταν ο χρήστης θέλει να βγει.
    Σε όλες τις άλλες περιπτώσεις επιστρέφει True ώστε ο caller να συνεχίσει.
    """
    action = intent.get("action", "unknown")
    target = intent.get("target", "").strip()
    reply = intent.get("reply", "")
    silent = intent.get("_silent", False)

    # --- Ειδικές ενέργειες ---

    if action == "stop_speaking":
        stop_speaking()
        return True

    if action == "answer_question":
        if silent:
            return True

        # Ημιτελής ερώτηση — ζητάμε διευκρίνιση
        if is_incomplete_question(target):
            followup = listen_for_followup("What would you like to know about, sir?")

            if followup:
                full_question = build_followup_question(target, followup)
                answer_general_question(full_question)
            else:
                speak_async("I did not catch that, sir.")

            return True

        answer_general_question(target)
        return True

    if action == "multi_action":
        steps = intent.get("steps", [])

        # Μιλάμε ΜΙΑ φορά για όλο το multi-command.
        speak_async(reply or "Executing your commands, sir.")
        time.sleep(1.5)

        # Τρέχουμε κάθε βήμα σιωπηλά για να μην πατάει το ένα την απάντηση
        # του άλλου.
        for step in steps:
            if isinstance(step, dict):
                step["_silent"] = True
                step["reply"] = ""
                perform_intent(step)
                time.sleep(1.0)

        return True

    # --- Ενέργειες στο filesystem ---

    if action == "open_app":
        if not target:
            say("What app should I open, sir?", silent)
            return True

        path = find_path(target, "app")
        if path:
            say(reply or f"Opening {target}, sir.", silent)
            launch_path(path)
        else:
            say(f"I could not find {target}, sir.", silent)

    elif action == "open_folder":
        if not target:
            say("What folder should I open, sir?", silent)
            return True

        path = find_path(target, "folder")
        if path:
            say(reply or f"Opening {target} folder, sir.", silent)
            launch_path(path)
        else:
            say(f"I could not find the {target} folder, sir.", silent)

    elif action == "open_file":
        if not target:
            say("What file should I open, sir?", silent)
            return True

        path = find_path(target, "file")
        if path:
            say(reply or f"Opening {target} file, sir.", silent)
            launch_path(path)
        else:
            say(f"I could not find {target}, sir.", silent)

    elif action == "close_app":
        if not target:
            say("What app should I close, sir?", silent)
            return True

        say(reply or f"Closing {target}, sir.", silent)
        close_app(target)

    # --- Web ενέργειες ---

    elif action == "web_search":
        if not target:
            say("What should I search for, sir?", silent)
            return True

        say(reply or f"Searching for {target}.", silent)
        open_google_search(target)

    elif action == "youtube_search":
        if not target:
            say("What should I play on YouTube, sir?", silent)
            return True

        say(reply or f"Playing {target} on YouTube.", silent)
        open_youtube_search(target)

    # --- Ενσωματωμένες πληροφορίες ---

    elif action == "get_time":
        say(datetime.datetime.now().strftime("The time is %I:%M %p, sir."), silent)

    elif action == "get_date":
        say(datetime.datetime.now().strftime("Today's date is %A, %B %d, %Y."), silent)

    elif action == "weather":
        # Απλή εκδοχή — ανοίγει Google search για τον καιρό
        say(reply or "Opening weather report.", silent)
        open_google_search("weather")

    elif action == "joke":
        say(random.choice([
            "Why don't scientists trust atoms? Because they make up everything.",
            "I'm afraid I can't let you do that... just kidding, sir.",
            "Why did the computer go to the doctor? Because it had a virus."
        ]), silent)

    elif action == "exit":
        say(reply or "JARVIS standing down.", silent)
        return False

    else:
        # Άγνωστο action
        say(reply or "I did not quite understand. Could you repeat that?", silent)

    return True


def execute_command(command):
    """Top-level: καθαρίζει το κείμενο, παίρνει intent, εκτελεί."""
    if not command.strip():
        return True

    command = clean_command(command)
    intent = agent_brain(command)
    result = perform_intent(intent)

    set_status("Listening")
    return result


# ---------------------------------------------------------------------------
# Wake-word handling
# ---------------------------------------------------------------------------

def remove_wake_word(text):
    """Αφαιρεί το 'jarvis' ώστε να μείνει μόνο η εντολή."""
    command = text
    for word in WAKE_WORDS:
        command = command.replace(word, "")
    return command.strip()


def contains_wake_word(text):
    """
    Word-boundary check: σπάει σε λέξεις και ψάχνει ακριβές match.
    Ένα απλό `"jarvis" in text` θα έπιανε και "travis" ή "service".
    """
    words = text.lower().split()
    return any(w in words for w in WAKE_WORDS)


def is_stop_command(command):
    """
    Ελαστικός εντοπισμός εντολής διακοπής.

    Το παλιό `command in STOP_PHRASES` απαιτούσε ΑΚΡΙΒΕΣ match, οπότε
    φράσεις όπως "stop please", "stop talking", "stop speaking now" ΔΕΝ
    πιάνονταν και ο JARVIS συνέχιζε να μιλάει.

    Τώρα:
    - κάνουμε strip τυχόν σημεία στίξης
    - θεωρούμε stop αν η εντολή ΕΙΝΑΙ ή ΑΡΧΙΖΕΙ με κάποια stop phrase
      (π.χ. "stop talking" → ξεκινάει με "stop" → stop)
    - επίσης αν ΠΕΡΙΕΧΕΙ μια stop phrase ως ξεχωριστό κομμάτι
    """
    if not command:
        return False

    # Καθάρισμα: πεζά + αφαίρεση κοινών σημείων στίξης στα άκρα
    cleaned = command.lower().strip().strip(".,!?;:")

    if not cleaned:
        return False

    for phrase in STOP_PHRASES:
        p = phrase.lower().strip()
        # ακριβές match  ή  ξεκινάει με τη φράση  ή  την περιέχει
        if cleaned == p or cleaned.startswith(p + " ") or f" {p} " in f" {cleaned} ":
            return True

    return False


def wake_callback(rec, audio):
    """
    Ενεργοποιείται από τον background listener του speech_recognition
    κάθε φορά που πιάνει φράση. Τρέχει σε worker thread, ΟΧΙ στο UI thread.
    """
    try:
        # Στέλνουμε το audio στον δωρεάν Google recognizer
        text = rec.recognize_google(audio, language=RECOGNITION_LANGUAGE).lower()
        add_log(f"HEARD: {text}")

        # Αγνοούμε ομιλίες χωρίς "jarvis"
        if not contains_wake_word(text):
            return

        # Ό,τι είπε μετά το wake word
        command = remove_wake_word(text)

        # ============================================================
        # ΔΙΟΡΘΩΣΗ — "jarvis stop": ελέγχεται ΠΡΩΤΟ απ' όλα.
        #
        # Αυτός ο έλεγχος πρέπει να γίνεται ΠΡΙΝ από τον έλεγχο
        # processing/is_speaking, γιατί όταν ο JARVIS μιλάει το
        # is_speaking είναι True και χωρίς αυτό το early return το
        # stop θα έβγαινε νωρίς αλλά ΧΩΡΙΣ να καλέσει stop_speaking().
        #
        # Χρησιμοποιούμε is_stop_command() (ελαστικό) αντί για το παλιό
        # `command in STOP_PHRASES` (που ήθελε ακριβές match), ώστε να
        # πιάνονται και "stop talking", "stop please", κ.λπ.
        # ============================================================
        if is_stop_command(command):
            add_log("⏹ STOP εντολή — διακοπή ομιλίας.")
            stop_speaking()
            # Καθαρίζουμε και την κατάσταση processing σε περίπτωση που
            # κάποια εντολή είχε κολλήσει.
            state.set(processing=False)
            set_status("Listening")
            return

        # Δεν δεχόμαστε νέα εντολή όσο επεξεργαζόμαστε ή μιλάμε
        if state.get("processing") or state.get("is_speaking"):
            return

        state.set(processing=True)
        set_status("Processing")

        # Είπε μόνο "jarvis" — ρωτάμε και ξανακούμε
        if not command:
            speak("Yes, sir?")
            time.sleep(0.3)

            with sr.Microphone() as source:
                audio_cmd = recognizer.listen(source, phrase_time_limit=8)

            try:
                command = recognizer.recognize_google(
                    audio_cmd,
                    language=RECOGNITION_LANGUAGE
                ).lower()
                add_log(f"COMMAND HEARD: {command}")
            except Exception:
                command = ""

        # Εκτέλεση εντολής. Αν επιστρέψει False, ο χρήστης είπε "exit".
        if not execute_command(command):
            # Είμαστε σε background thread. Δεν χρησιμοποιούμε os._exit
            # γιατί θα σκότωνε τη διεργασία πριν τελειώσει η φωνή του
            # αποχαιρετισμού και θα παρέκαμπτε το cleanup του Qt.
            # Περιμένουμε να ολοκληρωθεί κανονικά η εκφώνηση και ζητάμε
            # από το UI thread (μέσω signal) να κλείσει καθαρά.
            wait_until_silent(timeout=10.0)
            signals.request_exit.emit()

        state.set(processing=False)
        set_status("Listening")

    except Exception as e:
        # Catch-all — αν η Google API είναι κάτω, ή κόψει το internet,
        # δεν θέλουμε ένα κακό recognition να σκοτώσει το listener thread.
        print("Wake error:", e)
        state.set(processing=False)
        set_status("Listening")


# ---------------------------------------------------------------------------
# Toggle μικροφώνου
# ---------------------------------------------------------------------------

def toggle_microphone():
    """
    Εναλλάσσει την κατάσταση του μικροφώνου.

    Καλείται από το κουμπί "Mute Microphone" του UI:
    - Όταν το mic ακούει: σταματάει τον background listener ώστε να μην
      αναγνωρίζεται τίποτα — ούτε καν η λέξη αφύπνισης.
    - Όταν το mic είναι muted: ξεκινάει νέο background listener και
      αποθηκεύει τη νέα stop function στο state.

    Επιστρέφει:
    - True  → το microphone είναι ΤΩΡΑ muted
    - False → το microphone είναι ΤΩΡΑ ενεργό
    """
    if not state.mic_muted:
        # === ΣΕΝΑΡΙΟ 1: Είναι ενεργό → το κάνουμε mute ===
        # Καλούμε τη stop function που είχε επιστρέψει το
        # recognizer.listen_in_background(). Με wait_for_stop=False
        # δεν μπλοκάρουμε το UI thread.
        if state.stop_listening:
            try:
                state.stop_listening(wait_for_stop=False)
            except Exception as e:
                print(f"[mic] Σφάλμα κατά το σταμάτημα του listener: {e}")
            state.stop_listening = None

        state.set(mic_muted=True)
        set_status("Microphone OFF")
        add_log("🔇 Microphone muted.")
        return True

    else:
        # === ΣΕΝΑΡΙΟ 2: Είναι muted → το ξανα-ενεργοποιούμε ===
        # Ξεκινάμε νέο background listener με τον ίδιο wake_callback.
        # Σημείωση: το phrase_time_limit=6 πρέπει να ταιριάζει με αυτό
        # που χρησιμοποιείται στο start_assistant() του UI για συνέπεια.
        try:
            state.stop_listening = recognizer.listen_in_background(
                mic,
                wake_callback,
                phrase_time_limit=6
            )
        except Exception as e:
            # Αν αποτύχει η επανεκκίνηση (π.χ. το mic καταλήφθηκε από άλλη
            # εφαρμογή), παραμένουμε σε muted κατάσταση και ενημερώνουμε
            # τον χρήστη.
            print(f"[mic] Σφάλμα κατά την επανενεργοποίηση: {e}")
            add_log(f"Could not restart microphone: {e}")
            return True

        state.set(mic_muted=False)
        set_status("Listening")
        add_log("🎙 Microphone unmuted.")
        return False