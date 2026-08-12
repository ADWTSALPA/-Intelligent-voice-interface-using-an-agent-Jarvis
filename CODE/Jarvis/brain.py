"""
brain.py
--------
Layer AI / parsing εντολών.

Παίρνει το κείμενο του χρήστη και επιστρέφει ένα structured intent dict.

Παραδείγματα:
"open spotify"
-> {"action": "open_app", "target": "spotify", "reply": "Opening Spotify, sir."}

"open discord and open steam"
-> {
    "action": "multi_action",
    "reply": "Executing your commands, sir.",
    "steps": [
        {"action": "open_app", "target": "discord", "reply": "Opening Discord, sir."},
        {"action": "open_app", "target": "steam", "reply": "Opening Steam, sir."}
    ]
}
"""

import json

from .config import client, OPENAI_MODEL, add_log


# ---------------------------------------------------------------------------
# Καθαρισμός κειμένου
# ---------------------------------------------------------------------------

def clean_command(text):
    """
    Βασικός καθαρισμός φωνητικών εντολών.
    Αφαιρεί φιλικές λέξεις πριν στείλουμε στο AI ή τον offline parser.
    """
    text = text.lower().strip()

    removable = [
        "please",
        "can you",
        "could you",
        "would you",
        "for me",
        "now",
    ]

    for word in removable:
        text = text.replace(word, "")

    return " ".join(text.split())


# ---------------------------------------------------------------------------
# Εξαγωγή JSON
# ---------------------------------------------------------------------------

def extract_json(text):
    """
    Εξάγει JSON από την απάντηση του μοντέλου.
    Χειρίζεται και τις περιπτώσεις που το μοντέλο τυλίγει σε markdown fences.
    """
    text = text.strip()

    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()

    # Βρίσκουμε το εξωτερικό { ... }
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1 and end > start:
        text = text[start:end + 1]

    return json.loads(text)


# ---------------------------------------------------------------------------
# Offline parser (fallback)
# ---------------------------------------------------------------------------

def offline_brain(command):
    """
    Απλός τοπικός parser, χρησιμοποιείται όταν το OpenAI δεν είναι διαθέσιμο.
    Λιγότερο έξυπνος από το AI, αλλά κρατάει τις βασικές εντολές ζωντανές.
    """
    command = clean_command(command)

    stop_phrases = ["stop", "be quiet", "shut up", "stop speaking", "silence"]
    if command in stop_phrases:
        return {"action": "stop_speaking", "target": "", "reply": ""}

    # Γενικές ερωτήσεις
    if (
        command.startswith("tell me about ")
        or command.startswith("who is ")
        or command.startswith("what is ")
        or command.startswith("explain ")
        or command.startswith("how does ")
        or command.startswith("why does ")
        or command.startswith("why is ")
    ):
        return {"action": "answer_question", "target": command, "reply": ""}

    # Multi-action fallback:
    # "open discord and open steam"
    if " and " in command:
        parts = [p.strip() for p in command.split(" and ") if p.strip()]
        steps = []

        for part in parts:
            step = offline_brain(part)

            if step.get("action") != "unknown":
                steps.append(step)

        if len(steps) > 1:
            return {
                "action": "multi_action",
                "reply": "Executing your commands, sir.",
                "steps": steps,
            }

    open_words = ["open", "launch", "start"]
    close_words = ["close", "stop"]
    search_words = ["search", "google", "find"]
    youtube_words = ["youtube", "play"]

    # Κλείσιμο app
    if any(w in command for w in close_words):
        target = command

        for w in close_words:
            target = target.replace(w, "")

        target = target.strip()

        if not target:
            return {"action": "unknown", "target": "", "reply": ""}

        return {
            "action": "close_app",
            "target": target,
            "reply": f"Closing {target}, sir.",
        }

    # YouTube — έχει προτεραιότητα έναντι "search" ώστε
    # "play X on youtube" να πάει εδώ.
    if any(w in command for w in youtube_words):
        target = command

        for w in youtube_words:
            target = target.replace(w, "")

        target = target.replace("on", "").strip()

        if not target:
            return {"action": "unknown", "target": "", "reply": ""}

        return {
            "action": "youtube_search",
            "target": target,
            "reply": f"Playing {target} on YouTube.",
        }

    # Web search
    if any(w in command for w in search_words):
        target = command

        for w in search_words:
            target = target.replace(w, "")

        target = target.replace("on google", "").strip()

        if not target:
            return {"action": "unknown", "target": "", "reply": ""}

        return {
            "action": "web_search",
            "target": target,
            "reply": f"Searching for {target}.",
        }

    # Απλά triggers
    if "time" in command:
        return {"action": "get_time", "target": "", "reply": ""}

    if "date" in command:
        return {"action": "get_date", "target": "", "reply": ""}

    if "weather" in command:
        return {"action": "weather", "target": "", "reply": "Opening weather report."}

    if "joke" in command:
        return {"action": "joke", "target": "", "reply": ""}

    if any(x in command for x in ["goodbye", "sleep", "stand down", "exit"]):
        return {"action": "exit", "target": "", "reply": "JARVIS standing down."}

    # Άνοιγμα: app / folder / file
    if any(w in command for w in open_words):
        target = command

        for w in open_words:
            target = target.replace(w, "")

        target = target.strip()

        # "open downloads folder" -> open_folder
        if "folder" in target:
            target = target.replace("folder", "").strip()
            return {
                "action": "open_folder",
                "target": target,
                "reply": f"Opening {target} folder, sir.",
            }

        # "open my notes file" -> open_file
        if "file" in target:
            target = target.replace("file", "").strip()
            return {
                "action": "open_file",
                "target": target,
                "reply": f"Opening {target} file, sir.",
            }

        # Default: το θεωρούμε app
        return {
            "action": "open_app",
            "target": target,
            "reply": f"Opening {target}, sir.",
        }

    return {
        "action": "unknown",
        "target": "",
        "reply": "I did not quite understand. Could you repeat that?",
    }


# ---------------------------------------------------------------------------
# OpenAI agent parser
# ---------------------------------------------------------------------------

def agent_brain(user_text):
    """
    Χρησιμοποιεί το OpenAI για να μετατρέψει το κείμενο σε structured intent.
    Πέφτει στον offline_brain αν κάτι αποτύχει.
    """
    if client is None:
        return offline_brain(user_text)

    # Το system prompt μαθαίνει στο μοντέλο το schema μας και του δίνει
    # παραδείγματα. Όσο πιο σφιχτοί οι κανόνες τόσο πιο σταθερό το JSON.
    system_prompt = """
You are the intent parser for an English-only Windows voice assistant named JARVIS.

Your job:
Convert the user's command into JSON only.

Available actions:
- open_app
- open_folder
- open_file
- close_app
- web_search
- youtube_search
- get_time
- get_date
- weather
- joke
- answer_question
- stop_speaking
- multi_action
- exit
- unknown

Rules:
1. Return valid JSON only. No markdown. No explanation.
2. Do not invent unsupported actions.
3. Keep target short and clean.
4. If the user asks for a browser, use target "chrome".
5. If the user asks for something to write notes, use target "notepad".
6. If the user asks to search the web, use action "web_search".
7. If the user asks to play or watch something on YouTube, use action "youtube_search".
8. If the user asks a general question, says "tell me about", "who is", "what is", "explain", "how does", or "why", use action "answer_question".
9. If the user says "stop", "be quiet", "shut up", "silence", or "stop speaking", use action "stop_speaking".
10. If the user asks for more than one task, use "multi_action".
11. In "multi_action", each step must be one of the allowed actions.
12. For "multi_action", use reply "Executing your commands, sir."

Single action schema:
{"action":"open_app","target":"spotify","reply":"Opening Spotify, sir."}

Multi-action schema:
{"action":"multi_action","reply":"Executing your commands, sir.","steps":[{"action":"open_app","target":"discord","reply":"Opening Discord, sir."},{"action":"open_app","target":"steam","reply":"Opening Steam, sir."}]}

Examples:
User: open spotify
{"action":"open_app","target":"spotify","reply":"Opening Spotify, sir."}

User: open the downloads folder
{"action":"open_folder","target":"downloads","reply":"Opening downloads folder, sir."}

User: search Google for Python tutorials
{"action":"web_search","target":"Python tutorials","reply":"Searching for Python tutorials."}

User: play Eminem on YouTube
{"action":"youtube_search","target":"Eminem","reply":"Playing Eminem on YouTube."}

User: what time is it
{"action":"get_time","target":"","reply":""}

User: tell me about Elon Musk
{"action":"answer_question","target":"Tell me about Elon Musk","reply":""}

User: explain quantum computing
{"action":"answer_question","target":"Explain quantum computing","reply":""}

User: stop
{"action":"stop_speaking","target":"","reply":""}

User: open Discord and open Steam
{"action":"multi_action","reply":"Executing your commands, sir.","steps":[{"action":"open_app","target":"discord","reply":"Opening Discord, sir."},{"action":"open_app","target":"steam","reply":"Opening Steam, sir."}]}

User: open Chrome and search for AI news
{"action":"multi_action","reply":"Executing your commands, sir.","steps":[{"action":"open_app","target":"chrome","reply":"Opening Chrome, sir."},{"action":"web_search","target":"AI news","reply":"Searching for AI news."}]}
"""

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )

        text = response.output_text.strip()
        return extract_json(text)

    except Exception as e:
        # Network πρόβλημα, λάθος key, παράξενο JSON, κ.λπ. — gracefully fallback.
        add_log(f"Agent error: {e}. Using offline parser.")
        return offline_brain(user_text)


# ---------------------------------------------------------------------------
# Απάντηση γενικών ερωτήσεων
# ---------------------------------------------------------------------------

def answer_general_question(question):
    """
    Απαντάει σε κανονικές ερωτήσεις, όπως:
    "tell me about Elon Musk"
    "explain quantum computing"
    """
    if client is None:
        # Late import για να αποφύγουμε circular import
        from .voice import speak_async
        speak_async("I need the OpenAI API key to answer general questions, sir.")
        return

    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are JARVIS, a helpful English voice assistant. "
                        "Answer clearly, naturally, and briefly. "
                        "Keep the answer suitable for speaking out loud in about 2 to 5 sentences."
                    ),
                },
                {"role": "user", "content": question},
            ],
        )

        from .voice import speak_async
        answer = response.output_text.strip()
        speak_async(answer)

    except Exception as e:
        add_log(f"Answer error: {e}")
        from .voice import speak_async
        speak_async("I had trouble answering that, sir.")
