
"""
run_jarvis.py
-------------
Entry point για το PyInstaller build.

Αυτο το αρχειο πρεπει να βρισκεται ΕΞΩ απο τον φακελο Jarvis/
(δηλαδη στον γονικο φακελο, διπλα στο build.bat).

Δουλευει σαν wrapper: κανει absolute import του package και τρεχει
την main(), αποφευγοντας τα relative imports που δεν λειτουργουν
οταν το PyInstaller τρεχει το main.py απευθειας.
"""
from Jarvis.main import main

if __name__ == "__main__":
    main()