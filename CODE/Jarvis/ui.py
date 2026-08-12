"""
ui.py
-----
Το PySide6 UI για τον JARVIS.

Αναλαμβάνει:
- Το βασικό animated παράθυρο
- Τα κουμπιά
- Το log box
- Το status label
- Το dragging του παραθύρου
- Τα controls Exit/Minimize
"""

import math
import datetime

from PySide6.QtWidgets import QWidget, QPushButton, QTextEdit, QLabel, QApplication
from PySide6.QtCore import Qt, QTimer, QRectF
from PySide6.QtGui import (
    QPainter,
    QColor,
    QPen,
    QFont,
    QBrush,
    QRadialGradient,
    QLinearGradient,
)

from .config import state, signals
from .voice import speak_async
from .cache import reset_cache
# ΑΛΛΑΓΗ: εισάγουμε και την νέα toggle_microphone από τον executor
from .executor import wake_callback, toggle_microphone
from .voice import recognizer, mic


class JarvisUI(QWidget):
    def __init__(self):
        super().__init__()

        # --- Ρυθμίσεις παραθύρου ---
        self.setWindowTitle("JARVIS AI Assistant")
        self.setFixedSize(760, 650)
        # FramelessWindowHint = δεν υπάρχει title bar των Windows.
        # Σχεδιάζουμε το δικό μας και χειριζόμαστε μόνοι μας το dragging.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setStyleSheet("background-color: #050b14;")

        # --- Κατάσταση animation ---
        self.angle = 0          # γωνία περιστροφής για τα τόξα
        self.pulse = 0          # sine wave για τους παλμούς
        self.voice_active = False  # επιπλέον δαχτυλίδι όταν μιλάει
        self.scan_offset = 0    # κινούμενες οριζόντιες γραμμές
        self.old_pos = None     # tracking ποντικιού για drag

        self.init_ui()
        self.connect_signals()

        # 40 fps animation (1000ms / 25ms = 40fps)
        self.timer = QTimer()
        self.timer.timeout.connect(self.animate)
        self.timer.start(25)

    # ----------------------------------------------------------------------
    # Στήσιμο UI
    # ----------------------------------------------------------------------

    def init_ui(self):
        """Δημιουργεί όλα τα widgets και τα τοποθετεί σε σταθερές θέσεις."""

        # --- Τίτλος ---
        self.title = QLabel("JARVIS", self)
        self.title.setGeometry(255, 45, 310, 60)
        self.title.setStyleSheet("color: #22e6ff; background: transparent;")
        self.title.setFont(QFont("Arial", 42, QFont.Bold))

        self.subtitle = QLabel("Your Intelligent Desktop Assistant", self)
        self.subtitle.setGeometry(260, 105, 360, 26)
        self.subtitle.setStyleSheet("color: #9eeaff; background: transparent;")
        self.subtitle.setFont(QFont("Arial", 14))

        # --- Status badge ---
        self.status = QLabel("●  Status: Offline", self)
        self.status.setGeometry(255, 155, 250, 45)
        self.status.setAlignment(Qt.AlignCenter)
        self.status.setStyleSheet("""
            QLabel {
                color: #00eaff;
                background-color: rgba(0, 50, 90, 150);
                border: 1px solid #00bfff;
                border-radius: 5px;
                font-size: 20px;
                font-weight: bold;
            }
        """)

        # --- Βασικά κουμπιά ---
        self.start_btn = QPushButton("🎙   Start Assistant", self)
        self.start_btn.setGeometry(95, 270, 260, 65)
        self.start_btn.clicked.connect(self.start_assistant)

        # ΑΛΛΑΓΗ: το παλιό "Mute Voice" κουμπί αντικαταστάθηκε από
        # "Mute Microphone". Στην παλιά εκδοχή σταματούσε το TTS·
        # τώρα σταματάει τον background listener του recognizer,
        # ώστε ο βοηθός να μην ακούει τίποτα — ούτε καν τη λέξη
        # αφύπνισης — μέχρι ο χρήστης να ξανα-πατήσει το κουμπί.
        self.mic_btn = QPushButton("🎙   Mute Microphone", self)
        self.mic_btn.setGeometry(405, 270, 260, 65)
        self.mic_btn.clicked.connect(self.handle_mic_toggle)

        self.reset_btn = QPushButton("♻   Reset Cache", self)
        self.reset_btn.setGeometry(260, 365, 240, 50)
        self.reset_btn.clicked.connect(reset_cache)

        # --- Επαναχρησιμοποιούμενα styles για κουμπιά ---
        self.normal_blue = """
            QPushButton {
                background-color: rgba(7, 55, 105, 210);
                color: white;
                border: 2px solid #00bfff;
                border-radius: 18px;
                font-size: 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 150, 230, 220);
                border: 2px solid #00ffff;
            }
        """

        self.active_blue = """
            QPushButton {
                background-color: rgba(0, 150, 230, 230);
                color: white;
                border: 3px solid #7df5ff;
                border-radius: 18px;
                font-size: 20px;
                font-weight: bold;
            }
        """

        self.start_btn.setStyleSheet(self.normal_blue)
        self.mic_btn.setStyleSheet(self.normal_blue)
        self.reset_btn.setStyleSheet(self.normal_blue)

        # --- Log section ---
        self.log_title = QLabel("●  J.A.R.V.I.S  LOG", self)
        self.log_title.setGeometry(65, 495, 260, 25)
        self.log_title.setStyleSheet("color: #00eaff; background: transparent;")
        self.log_title.setFont(QFont("Consolas", 15, QFont.Bold))

        self.log = QTextEdit(self)
        self.log.setGeometry(50, 525, 660, 85)
        self.log.setReadOnly(True)
        self.log.setText("SYSTEM READY...")
        self.log.setStyleSheet("""
            QTextEdit {
                background-color: rgba(0, 7, 18, 210);
                color: #8df6ff;
                border: 2px solid #00bfff;
                border-radius: 14px;
                font-family: Consolas;
                font-size: 13px;
                padding: 10px;
            }
        """)

        # --- Custom window controls (αφού κρύψαμε αυτά των Windows) ---
        self.close_btn = QPushButton("×", self)
        self.close_btn.setGeometry(710, 25, 28, 28)
        self.close_btn.clicked.connect(self.exit_app)

        self.min_btn = QPushButton("—", self)
        self.min_btn.setGeometry(675, 25, 28, 28)
        self.min_btn.clicked.connect(self.showMinimized)

        mini_style = """
            QPushButton {
                background-color: rgba(0, 20, 35, 190);
                color: #7df5ff;
                border: 1px solid #00d9ff;
                border-radius: 8px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(0, 217, 255, 100);
                color: white;
            }
        """

        self.min_btn.setStyleSheet(mini_style)
        self.close_btn.setStyleSheet(mini_style)

    def connect_signals(self):
        """Συνδέει τα background-thread signals με slots του UI."""
        signals.log.connect(self.add_log)
        signals.status.connect(self.set_status)
        signals.voice_active.connect(self.set_voice_active)
        signals.request_exit.connect(self.exit_app)

    # ----------------------------------------------------------------------
    # Ενέργειες κουμπιών
    # ----------------------------------------------------------------------

    def start_assistant(self):
        """Ξεκινάει τον background listener για να αρχίσει η ακρόαση."""
        if state.assistant_running:
            self.add_log("Assistant is already online.")
            return

        state.set(assistant_running=True)

        self.set_status("Listening")
        self.add_log("Assistant started.")
        self.add_log("Agent Jarvis online.")

        speak_async("JARVIS online. Awaiting your command, sir.")

        # Το listen_in_background επιστρέφει μια συνάρτηση stop που θα
        # τη χρησιμοποιήσουμε όταν κλείνει η εφαρμογή ή όταν ο χρήστης
        # πατήσει Mute Microphone.
        state.stop_listening = recognizer.listen_in_background(
            mic,
            wake_callback,
            phrase_time_limit=6
        )

        # Visual feedback ότι τα δύο κουμπιά είναι πλέον ενεργά:
        # - start_btn: active style γιατί ο assistant τρέχει
        # - mic_btn:   active style γιατί το microphone ακούει
        self.start_btn.setStyleSheet(self.active_blue)
        self.mic_btn.setStyleSheet(self.active_blue)

    # ΑΛΛΑΓΗ: το παλιό toggle_voice() αντικαταστάθηκε από αυτή τη μέθοδο.
    # Πια δεν αλλάζει το VOICE_ENABLED — αντί γι' αυτό καλεί την
    # toggle_microphone() του executor που σταματάει/ξεκινάει τον listener.
    def handle_mic_toggle(self):
        """Mute/Unmute μικροφώνου μέσω της toggle_microphone() του executor."""
        # Δεν έχει νόημα να κάνουμε mute πριν ξεκινήσει ο assistant.
        if not state.assistant_running:
            self.add_log("Press Start Assistant first.")
            return

        # Καλούμε την backend logic. Επιστρέφει True αν είναι ΤΩΡΑ muted.
        is_muted_now = toggle_microphone()

        if is_muted_now:
            # Κατάσταση MUTED: σβησμένο κουμπί + text προτροπή unmute
            self.mic_btn.setText("🔇   Unmute Microphone")
            self.mic_btn.setStyleSheet(self.normal_blue)
        else:
            # Κατάσταση LISTENING: φωτεινό κουμπί + text προτροπή mute
            self.mic_btn.setText("🎙   Mute Microphone")
            self.mic_btn.setStyleSheet(self.active_blue)

        # Επανασχεδίαση για τα glow effects γύρω από το κουμπί.
        self.update()

    def exit_app(self):
        """Σταματάει τον background listener και κλείνει την εφαρμογή."""
        try:
            if state.stop_listening:
                # wait_for_stop=False -> δεν μπλοκάρουμε το UI thread
                state.stop_listening(wait_for_stop=False)
        except Exception:
            pass

        QApplication.quit()

    # ----------------------------------------------------------------------
    # Slots (καλούνται από signals worker threads)
    # ----------------------------------------------------------------------

    def set_status(self, text):
        self.status.setText(f"●  Status: {text}")

    def add_log(self, text):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.log.append(f"[{timestamp}] {text}")

    def set_voice_active(self, active):
        # Ενεργοποιεί το επιπλέον δαχτυλίδι παλμού στο paintEvent
        self.voice_active = active

    # ----------------------------------------------------------------------
    # Animation / paint
    # ----------------------------------------------------------------------

    def animate(self):
        """Τρέχει κάθε 25ms — αυξάνει counters και ζητάει repaint."""
        self.angle = (self.angle + 3) % 360
        self.pulse = (self.pulse + 0.07) % (math.pi * 2)
        self.scan_offset = (self.scan_offset + 1) % 18
        self.update()  # προγραμματίζει paintEvent

    def paintEvent(self, event):
        """Σχεδιάζει χειροκίνητα το HUD: gradient, grid, δαχτυλίδια, πυρήνας."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # --- Φόντο ---
        painter.fillRect(self.rect(), QColor("#050b14"))

        # --- Κύριο panel με κάθετο gradient ---
        main_rect = QRectF(8, 8, 744, 634)

        bg = QLinearGradient(0, 8, 760, 642)
        bg.setColorAt(0, QColor(5, 18, 40))
        bg.setColorAt(1, QColor(0, 6, 18))

        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(QColor("#0aaaff"), 2))
        painter.drawRoundedRect(main_rect, 18, 18)

        # --- Εξωτερικά glow rings ---
        for i, alpha in enumerate([80, 40, 20]):
            painter.setPen(QPen(QColor(0, 200, 255, alpha), 2 + i))
            painter.drawRoundedRect(main_rect.adjusted(-i, -i, i, i), 20, 20)

        # --- Animated horizontal grid (scan lines) ---
        painter.setPen(QPen(QColor(0, 140, 220, 45), 1))
        for y in range(50 + self.scan_offset, 615, 18):
            painter.drawLine(35, y, 725, y)

        # --- Vertical grid (στατικό) ---
        painter.setPen(QPen(QColor(0, 140, 220, 22), 1))
        for x in range(45, 725, 40):
            painter.drawLine(x, 50, x, 615)

        # --- Iron Man-style arc reactor ---
        cx, cy = 145, 155
        # Πιο έντονο φως όταν ο JARVIS μιλάει
        glow_strength = 150 if self.voice_active else 90

        glow = QRadialGradient(cx, cy, 140)
        glow.setColorAt(0, QColor(0, 230, 255, glow_strength))
        glow.setColorAt(0.3, QColor(0, 120, 255, 45))
        glow.setColorAt(1, QColor(0, 0, 0, 0))

        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(cx - 130, cy - 130, 260, 260)

        # --- Παλλόμενα δαχτυλίδια ---
        painter.setBrush(Qt.NoBrush)

        # Sine wave μεταξύ 70 και 230 alpha → εφέ παλμού
        pulse_alpha = int(150 + 80 * math.sin(self.pulse))

        # Επιπλέον εξωτερικό δαχτυλίδι όταν μιλάει
        if self.voice_active:
            voice_radius = int(105 + 8 * math.sin(self.pulse))
            painter.setPen(QPen(QColor(0, 230, 255, 110), 3))
            painter.drawEllipse(
                cx - voice_radius,
                cy - voice_radius,
                voice_radius * 2,
                voice_radius * 2
            )

        # Ομόκεντρα δαχτυλίδια — το εξωτερικό παλμώνει, τα εσωτερικά όχι
        for radius, width, alpha in [
            (95, 4, pulse_alpha),
            (75, 3, 230),
            (55, 2, 210),
            (35, 2, 200),
        ]:
            painter.setPen(QPen(QColor(0, 230, 255, alpha), width))
            painter.drawEllipse(cx - radius, cy - radius, radius * 2, radius * 2)

        # --- Περιστρεφόμενα τόξα ---
        # save() για να μην επηρεαστούν τα παρακάτω από τη rotation
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.angle)

        # Εξωτερικά τόξα (light cyan)
        # Το drawArc παίρνει γωνίες σε 1/16 της μοίρας — εξ ου το * 16
        painter.setPen(QPen(QColor("#7df5ff"), 7))
        painter.drawArc(QRectF(-83, -83, 166, 166), 20 * 16, 100 * 16)
        painter.drawArc(QRectF(-83, -83, 166, 166), 200 * 16, 90 * 16)

        # Εσωτερικά τόξα (πιο σκούρα μπλε)
        painter.setPen(QPen(QColor("#00aaff"), 4))
        painter.drawArc(QRectF(-62, -62, 124, 124), 90 * 16, 80 * 16)
        painter.drawArc(QRectF(-62, -62, 124, 124), 260 * 16, 70 * 16)

        painter.restore()  # αναιρεί το translate/rotate

        # --- Λευκός πυρήνας στο κέντρο ---
        core = QRadialGradient(cx, cy, 24)
        core.setColorAt(0, QColor(255, 255, 255))
        core.setColorAt(0.4, QColor(0, 230, 255))
        core.setColorAt(1, QColor(0, 100, 200, 50))

        painter.setBrush(QBrush(core))
        painter.setPen(QPen(QColor("#9fffff"), 2))
        painter.drawEllipse(cx - 12, cy - 12, 24, 24)

        # --- Διακριτικό glow γύρω από κάθε κουμπί ---
        glow_color = QColor(0, 217, 255, 55)
        for rect in [
            QRectF(95, 270, 260, 65),    # Start
            QRectF(405, 270, 260, 65),   # Mute Microphone  (ΑΛΛΑΓΗ: σχόλιο)
            QRectF(260, 365, 240, 50),   # Reset
        ]:
            for i in range(3):
                painter.setPen(QPen(glow_color, 2 + i))
                painter.drawRoundedRect(rect.adjusted(-i, -i, i, i), 18, 18)

        # --- Border γύρω από το log box ---
        painter.setPen(QPen(QColor("#00bfff"), 2))
        painter.drawRoundedRect(QRectF(50, 525, 660, 85), 14, 14)

    # ----------------------------------------------------------------------
    # Window dragging — το κάνουμε χειροκίνητα γιατί κρύψαμε το title bar
    # ----------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.old_pos = event.globalPosition().toPoint()

    def mouseMoveEvent(self, event):
        if self.old_pos:
            # Μετακινούμε το παράθυρο κατά τη διαφορά από την προηγούμενη θέση
            delta = event.globalPosition().toPoint() - self.old_pos
            self.move(self.x() + delta.x(), self.y() + delta.y())
            self.old_pos = event.globalPosition().toPoint()

    def mouseReleaseEvent(self, event):
        self.old_pos = None