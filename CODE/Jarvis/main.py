"""
main.py
-------
Το entry point του JARVIS.

Τρέξε από τον γονικό φάκελο με:

    python -m Jarvis.main

Γιατί `python -m`; Τα modules χρησιμοποιούν relative imports (από το `.config`),
που απαιτούν να τρέχουν ως μέρος πακέτου. Τρέχοντας απευθείας το main.py
θα αποτύχει με ImportError.
"""

import sys

from PySide6.QtWidgets import QApplication

from .ui import JarvisUI


def main():
    # Κάθε εφαρμογή Qt χρειάζεται ακριβώς ΕΝΑ QApplication.
    # Είναι αυτό που τρέχει το event loop.
    app = QApplication(sys.argv)

    # Δημιουργία και εμφάνιση του παραθύρου JARVIS
    ui = JarvisUI()
    ui.show()

    # Τρέχει το event loop. Το exec() μπλοκάρει εδώ μέχρι να κλείσει το
    # παράθυρο, μετά επιστρέφει exit code που τον δίνουμε πίσω στο OS.
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
