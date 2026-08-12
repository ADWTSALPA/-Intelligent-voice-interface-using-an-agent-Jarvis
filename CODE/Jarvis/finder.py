"""
finder.py
---------
Layer τοπικών εργαλείων για Windows.

Αναλαμβάνει:
- Άνοιγμα εφαρμογών, φακέλων, αρχείων
- Κλείσιμο εφαρμογών
- Google search
- YouTube search
- Έξυπνη αναζήτηση με cache
"""

import os
import subprocess
import urllib.parse
import difflib  # για fuzzy string matching ως τελευταίο fallback

from .cache import load_cache, save_cache


# ---------------------------------------------------------------------------
# Σταθερές αναζήτησης
# ---------------------------------------------------------------------------

# Όριο βάθους για το os.walk ώστε η αναζήτηση να μην κατεβαίνει
# υπερβολικά βαθιά στο Program Files και κρατάει χρόνο απόκρισης.
MAX_WALK_DEPTH = 4


# ---------------------------------------------------------------------------
# Βοηθητικά
# ---------------------------------------------------------------------------

def normalize_name(text):
    """
    Καθαρίζει το όνομα ώστε "vs code" να ταιριάζει με "VS_Code"
    και "vs-code.exe".
    """
    return (
        text.lower()
        .replace("_", " ")
        .replace("-", " ")
        .replace(".", " ")
        .replace("  ", " ")  # Συμπτύσσει διπλά κενά
        .strip()
    )


def _resolve_bare_exe(exe_name):
    """
    Παίρνει ένα  σκέτου ονόματος εκτελέσιμου (π.χ. "powerpnt.exe"),
    βρίσκει το πλήρες path του μέσω του App Paths registry — το ίδιο
    μέρος όπου ψάχνει το Win+R dialog των Windows.

    Επιστρέφει πλήρες path ή None.

    Χρειάζεται για εφαρμογές που δεν είναι στο Windows PATH, όπως
    το Microsoft Office (winword.exe, excel.exe, powerpnt.exe), τα
    οποία είναι καταχωρημένα μόνο στο App Paths registry.
    """
    try:
        import winreg
    except ImportError:
        return None

    locations = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    ]

    for hive, subkey in locations:
        try:
            with winreg.OpenKey(hive, subkey + "\\" + exe_name) as key:
                path, _ = winreg.QueryValueEx(key, "")
                if path:
                    path = path.strip('"').strip()
                    if os.path.exists(path):
                        return path
        except OSError:
            continue

    return None


def launch_path(path):
    """
    Ανοίγει ένα Windows path, εκτελέσιμο, shell command ή URI.
    """
    try:
        # UWP apps (Microsoft Store) — π.χ. Netflix, Spotify (Store version),
        # Disney+, WhatsApp Store, κ.λπ. Δεν είναι κανονικά .exe — ανοίγουν
        # μόνο μέσω του "shell:AppsFolder\<PackageFamilyName>!App" του Windows
        # Explorer.
        if path.startswith("uwp:"):
            shell_path = path[4:]
            subprocess.Popen(
                ["explorer.exe", shell_path],
                shell=False
            )
            return

        if path.endswith(":"):
            # Protocol handler (π.χ. "ms-settings:")
            os.startfile(path)
        elif path.endswith(".msc"):
            # Management consoles (Device Manager κ.λπ.)
            subprocess.Popen(path, shell=True)
        elif path.endswith(".exe") and not os.path.exists(path):
            # Σκέτο όνομα exe — π.χ. "powerpnt.exe". Ψάχνουμε στο
            # App Paths registry (το ίδιο μέρος που χρησιμοποιεί το
            # Win+R) για να βρούμε το πλήρες path. Έτσι λειτουργούν
            # σωστά εφαρμογές όπως το Office που δεν είναι στο PATH.
            resolved = _resolve_bare_exe(os.path.basename(path))
            if resolved:
                os.startfile(resolved)
            else:
                # Αν δεν βρεθεί στο registry, βασιζόμαστε στο PATH
                subprocess.Popen(path, shell=True)
        else:
            # Κανονικό αρχείο/φάκελος — αφήνουμε τα Windows να επιλέξουν app
            os.startfile(path)
    except Exception as e:
        # Log για debugging και έσχατη προσπάθεια
        print(f"[launch] Σφάλμα ανοίγματος '{path}': {e}")
        try:
            subprocess.Popen(path, shell=True)
        except Exception as e2:
            print(f"[launch] Fallback απέτυχε επίσης: {e2}")


# ---------------------------------------------------------------------------
# Γνωστές εφαρμογές / φάκελοι
# ---------------------------------------------------------------------------

# Lookup table για άμεση εύρεση χωρίς να ψάξουμε στον δίσκο.
# Τα keys είναι αυτά που μπορεί να πει ο χρήστης.
# Τα values είναι λίστες με υποψήφια paths — κερδίζει το πρώτο που υπάρχει.
KNOWN_OPEN_APPS = {
    # Βασικά Windows
    "calculator": ["calc.exe"],
    "calc": ["calc.exe"],
    "settings": ["ms-settings:"],
    "setting": ["ms-settings:"],
    "windows settings": ["ms-settings:"],
    "control panel": ["control.exe"],
    "paint": ["mspaint.exe"],
    "notepad": ["notepad.exe"],
    "wordpad": ["write.exe"],

    # Microsoft Office
    "word": ["winword.exe"],
    "microsoft word": ["winword.exe"],
    "powerpoint": ["powerpnt.exe"],
    "microsoft powerpoint": ["powerpnt.exe"],
    "excel": ["excel.exe"],
    "microsoft excel": ["excel.exe"],
    "outlook": ["outlook.exe"],
    "microsoft outlook": ["outlook.exe"],
    "onenote": ["onenote.exe"],
    "teams": ["ms-teams.exe"],

    # Εργαλεία developer
    "vs code": ["code.exe"],
    "visual studio code": ["code.exe"],
    "code": ["code.exe"],
    "visual studio": ["devenv.exe"],

    # Browsers
    "edge": ["msedge.exe"],
    "microsoft edge": ["msedge.exe"],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        "chrome.exe",
    ],
    "firefox": ["firefox.exe"],
    "brave": ["brave.exe"],
    "opera": ["opera.exe"],

    # Media / launchers
    "spotify": [
        os.path.expanduser("~/AppData/Roaming/Spotify/Spotify.exe"),
        os.path.expanduser("~/AppData/Local/Microsoft/WindowsApps/Spotify.exe"),
        "Spotify.exe",
    ],
    "steam": [
        r"C:\Program Files (x86)\Steam\steam.exe",
        r"C:\Program Files\Steam\steam.exe",
        "steam.exe",
    ],
    "epic": [
        r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
        r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    ],
    "epic games": [
        r"C:\Program Files (x86)\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
        r"C:\Program Files\Epic Games\Launcher\Portal\Binaries\Win32\EpicGamesLauncher.exe",
    ],
    "riot": [r"C:\Riot Games\Riot Client\RiotClientServices.exe"],
    "league": [r"C:\Riot Games\Riot Client\RiotClientServices.exe"],
    "league of legends": [r"C:\Riot Games\Riot Client\RiotClientServices.exe"],

    # Εργαλεία συστήματος
    "task manager": ["taskmgr.exe"],
    "device manager": ["devmgmt.msc"],
    "disk management": ["diskmgmt.msc"],
    "services": ["services.msc"],
    "registry editor": ["regedit.exe"],
    "regedit": ["regedit.exe"],
    "file explorer": ["explorer.exe"],
    "explorer": ["explorer.exe"],
    "cmd": ["cmd.exe"],
    "command prompt": ["cmd.exe"],
    "powershell": ["powershell.exe"],
    "terminal": ["wt.exe"],

    # Windows Store apps / URI schemes
    "snipping tool": ["snippingtool.exe", "ms-screenclip:"],
    "camera": ["microsoft.windows.camera:"],
    "photos": ["ms-photos:"],
    "mail": ["outlookmail:"],
    "calendar": ["outlookcal:"],
    "store": ["ms-windows-store:"],
    "microsoft store": ["ms-windows-store:"],

    # Φάκελοι χρήστη
    "downloads": [os.path.expanduser("~/Downloads")],
    "documents": [os.path.expanduser("~/Documents")],
    "desktop": [os.path.expanduser("~/Desktop")],
    "pictures": [os.path.expanduser("~/Pictures")],
    "videos": [os.path.expanduser("~/Videos")],
    "music": [os.path.expanduser("~/Music")],
    "screenshots": [os.path.expanduser("~/Pictures/Screenshots")],
    "screenshot folder": [os.path.expanduser("~/Pictures/Screenshots")],
}


# Φάκελοι όπου ψάχνουμε αν δεν βρούμε κάτι στους KNOWN_OPEN_APPS.
# Σειρά: από τα φθηνότερα/πιθανότερα προς τα ακριβότερα.
SEARCH_DIRS = [
    # Φάκελοι χρήστη (γρήγορο walk)
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Downloads"),
    os.path.expanduser("~/Pictures"),
    os.path.expanduser("~/Videos"),
    os.path.expanduser("~/Music"),
    os.path.expanduser("~/OneDrive"),

    # AppData — όπου εγκαθίστανται οι περισσότερες apps του χρήστη
    os.path.expanduser("~/AppData/Roaming/Spotify"),
    os.path.expanduser("~/AppData/Local/Microsoft/WindowsApps"),
    os.path.expanduser("~/AppData/Roaming/Microsoft/Windows/Start Menu/Programs"),
    os.path.expanduser("~/AppData/Local/Programs"),
    os.path.expanduser("~/AppData/Local"),

    # Εγκαταστάσεις σε επίπεδο συστήματος (μεγάλα — προστασία με depth limit)
    r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
    r"C:\Program Files",
    r"C:\Program Files (x86)",

    # Φάκελοι παιχνιδιών
    r"C:\XboxGames",
    r"C:\Games",
    r"D:\Games",
    r"E:\Games",
    r"D:\SteamLibrary",
    r"E:\SteamLibrary",
    r"C:\Program Files (x86)\Steam\steamapps\common",
    r"C:\Riot Games",
    r"C:\Epic Games",
]


APP_EXTENSIONS = (".exe", ".lnk", ".url")
FILE_EXTENSIONS = (
    ".txt", ".pdf", ".docx", ".xlsx", ".pptx",
    ".png", ".jpg", ".jpeg", ".mp4", ".mp3",
    ".py", ".zip", ".rar"
)


# ---------------------------------------------------------------------------
# Αναζήτηση UWP / Microsoft Store apps
# ---------------------------------------------------------------------------

# Cache του πλήρους λίστας UWP apps. Η κλήση στο PowerShell είναι αργή
# (~1-2 δευτερόλεπτα), οπότε την κάνουμε ΜΙΑ ΦΟΡΑ ανά session και την
# κρατάμε εδώ στη μνήμη.
_uwp_apps_cache = None


def _get_uwp_apps():
    """
    Επιστρέφει dict με όλες τις εγκατεστημένες UWP/Store apps στη μορφή:
        { "netflix": "shell:AppsFolder\\4DF9E0F8.Netflix_...!App", ... }

    Χρησιμοποιεί το PowerShell cmdlet Get-StartApps που γυρνάει ό,τι βλέπει
    το Start Menu — και κανονικά apps και UWP. Εμείς κρατάμε όσα έχουν
    AppID με "!" (η μορφή PackageFamilyName!AppId σημαίνει UWP).
    """
    global _uwp_apps_cache
    if _uwp_apps_cache is not None:
        return _uwp_apps_cache

    apps = {}

    try:
        # -NoProfile -> πιο γρήγορη εκκίνηση
        # -Command  -> εκτέλεση string
        # Get-StartApps επιστρέφει Name + AppID (PackageFamilyName!App)
        # Το ConvertTo-Csv το κάνει εύκολα parsable
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-WindowStyle", "Hidden",
                "-Command",
                "Get-StartApps | ConvertTo-Csv -NoTypeInformation",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            # CREATE_NO_WINDOW = 0x08000000 — να μην εμφανιστεί παράθυρο
            # PowerShell όταν τρέχουμε από GUI Qt εφαρμογή.
            creationflags=0x08000000 if os.name == "nt" else 0,
        )

        if result.returncode != 0:
            _uwp_apps_cache = apps
            return apps

        lines = result.stdout.strip().splitlines()
        # Πρώτη γραμμή είναι το header ("Name","AppID") — την παρακάμπτουμε.
        for line in lines[1:]:
            # Format: "App Name","PackageFamilyName!AppId"
            # Κάνουμε απλό CSV split — δεν έχουμε ποτέ commas μέσα στα
            # ονόματα start menu apps.
            parts = [p.strip().strip('"') for p in line.split('","')]
            if len(parts) < 2:
                # fallback split
                parts = [p.strip().strip('"') for p in line.split(",", 1)]
                if len(parts) < 2:
                    continue

            name = parts[0]
            app_id = parts[1].rstrip('"')

            # Μόνο UWP apps έχουν "!" στο AppID (PackageFamilyName!App).
            # Τα κανονικά .exe από το Start Menu έχουν path που τελειώνει
            # σε .exe — αυτά τα πιάνει ήδη ο υπάρχων μηχανισμός.
            if "!" not in app_id:
                continue

            apps[normalize_name(name)] = f"shell:AppsFolder\\{app_id}"

    except Exception as e:
        print(f"[uwp] Σφάλμα κατά την ανίχνευση UWP apps: {e}")

    _uwp_apps_cache = apps
    return apps


def find_uwp_app(name):
    """
    Ψάχνει UWP/Store app με το όνομα που δίνει ο χρήστης.

    Στρατηγική:
    1. Ακριβές match στο normalized name
    2. Partial match: το όνομα του χρήστη περιέχεται στο app name
    3. Partial match αντίστροφα: app name περιέχεται στο όνομα χρήστη

    Επιστρέφει string με πρόθεμα "uwp:" που το launch_path() αναγνωρίζει,
    ή None αν δεν βρει.
    """
    name = normalize_name(name)
    apps = _get_uwp_apps()

    if not apps:
        return None

    # 1. Ακριβές match
    if name in apps:
        return f"uwp:{apps[name]}"

    # 2. Το user query είναι αρχή του app name (π.χ. "netflix" σε "netflix")
    #    ή περιέχεται στο app name (π.χ. "spotify" σε "spotify music")
    for app_name, shell_path in apps.items():
        if app_name.startswith(name + " ") or app_name == name:
            return f"uwp:{shell_path}"

    # 3. Πιο χαλαρό partial match
    for app_name, shell_path in apps.items():
        if name in app_name.split():
            return f"uwp:{shell_path}"

    return None


# ---------------------------------------------------------------------------
# Επίπεδο 3 — Windows Registry (εγκατεστημένα προγράμματα)
#
# Όταν εγκαθιστάς ένα πρόγραμμα στα Windows (Discord, Zoom, VLC, OBS, GIMP,
# Steam, παιχνίδια κ.λπ.), ο installer γράφει στο registry σε δύο κλειδιά:
#   HKLM\...\Uninstall  — για όλους τους χρήστες
#   HKCU\...\Uninstall  — μόνο για τον τρέχοντα χρήστη
# Διαβάζοντας αυτά τα κλειδιά μαθαίνουμε όνομα + InstallLocation/DisplayIcon
# χωρίς να σκανάρουμε ολόκληρο τον δίσκο.
# ---------------------------------------------------------------------------

_installed_apps_cache = None


def _get_installed_apps():
    """
    Επιστρέφει dict { normalized_name: exe_path } για όλα τα προγράμματα
    που είναι καταχωρημένα στο registry ως εγκατεστημένα.

    Καλείται ΜΙΑ φορά ανά session — από εκεί και κάτω είναι ακαριαίο.
    """
    global _installed_apps_cache
    if _installed_apps_cache is not None:
        return _installed_apps_cache

    apps = {}

    # winreg είναι Windows-only stdlib module
    try:
        import winreg
    except ImportError:
        _installed_apps_cache = apps
        return apps

    # Κλειδιά registry όπου ζουν τα εγκατεστημένα προγράμματα.
    # Σαρώνουμε και τις τρεις τοποθεσίες για πλήρη κάλυψη.
    registry_locations = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    ]

    for hive, subkey_path in registry_locations:
        try:
            with winreg.OpenKey(hive, subkey_path) as parent_key:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(parent_key, i)
                        i += 1
                    except OSError:
                        break  # τέλος

                    try:
                        with winreg.OpenKey(parent_key, subkey_name) as sub:
                            # Πάρε το DisplayName
                            try:
                                name, _ = winreg.QueryValueEx(sub, "DisplayName")
                            except OSError:
                                continue

                            # Σκιπάρουμε updates, hotfixes κ.λπ. που δεν είναι
                            # κανονικές εφαρμογές
                            name_lower = name.lower()
                            if any(skip in name_lower for skip in [
                                "update for", "hotfix", "security update",
                                "kb9", "kb5", "kb4", "kb3", "redistributable",
                            ]):
                                continue

                            # Δοκίμασε διάφορα πεδία για το exe path
                            exe_path = None
                            for value_name in ("DisplayIcon", "InstallLocation"):
                                try:
                                    v, _ = winreg.QueryValueEx(sub, value_name)
                                    if v:
                                        # Το DisplayIcon είναι συνήθως exe,
                                        # αν περιέχει "," είναι "path,index"
                                        if "," in v and value_name == "DisplayIcon":
                                            v = v.split(",")[0]
                                        v = v.strip('"').strip()
                                        if v.lower().endswith(".exe") and os.path.exists(v):
                                            exe_path = v
                                            break
                                        if value_name == "InstallLocation" and os.path.isdir(v):
                                            # Αν είναι folder, ψάχνουμε για το exe
                                            # με όνομα κοντινό στο DisplayName
                                            candidate = _guess_exe_in_folder(v, name)
                                            if candidate:
                                                exe_path = candidate
                                                break
                                except OSError:
                                    continue

                            if exe_path:
                                apps[normalize_name(name)] = exe_path

                    except OSError:
                        continue
        except OSError:
            continue

    _installed_apps_cache = apps
    return apps


def _guess_exe_in_folder(folder, app_name):
    """
    Δεδομένου ενός InstallLocation folder και του DisplayName της εφαρμογής,
    προσπαθεί να βρει το πιο πιθανό .exe μέσα στον φάκελο.

    Στρατηγική: ψάχνει .exe με όνομα που ταιριάζει στο app_name.
    """
    try:
        normalized_app = normalize_name(app_name)
        candidates = []
        for entry in os.listdir(folder):
            full = os.path.join(folder, entry)
            if not os.path.isfile(full) or not entry.lower().endswith(".exe"):
                continue
            exe_base = normalize_name(os.path.splitext(entry)[0])
            # Πιο σχετικό = πιο όμοιο με το app name
            if normalized_app == exe_base or exe_base in normalized_app or normalized_app in exe_base:
                candidates.append(full)

        if candidates:
            # Προτίμησε το συντομότερο όνομα (συνήθως είναι το κύριο exe)
            return min(candidates, key=lambda p: len(os.path.basename(p)))
    except OSError:
        pass
    return None


def find_installed_app(name):
    """Ψάχνει την εφαρμογή στα εγκατεστημένα προγράμματα του registry."""
    name = normalize_name(name)
    apps = _get_installed_apps()
    if not apps:
        return None

    # 1. Ακριβές match
    if name in apps:
        return apps[name]

    # 2. Το user query είναι αρχή ή υποσύνολο του DisplayName
    for app_name, exe_path in apps.items():
        if app_name.startswith(name + " ") or name in app_name.split():
            return exe_path

    # 3. Αρκετά χαλαρό partial match
    for app_name, exe_path in apps.items():
        if name in app_name:
            return exe_path

    return None


# ---------------------------------------------------------------------------
# Επίπεδο 4 — Start Menu shortcuts (.lnk αρχεία)
#
# Όλα τα προγράμματα που εμφανίζονται στο Start Menu έχουν shortcut σε:
#   C:\ProgramData\Microsoft\Windows\Start Menu\Programs           (system-wide)
#   %APPDATA%\Microsoft\Windows\Start Menu\Programs                (user)
# Πιάνει εφαρμογές που γλίτωσαν από το registry (π.χ. portable με χειροκίνητο
# shortcut, παιχνίδια από Steam/Epic, παλιά προγράμματα).
# ---------------------------------------------------------------------------

_start_menu_cache = None


def _get_start_menu_shortcuts():
    """Επιστρέφει dict { normalized_name: path_to_lnk } για όλα τα Start Menu."""
    global _start_menu_cache
    if _start_menu_cache is not None:
        return _start_menu_cache

    shortcuts = {}
    roots = [
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        os.path.expanduser(r"~\AppData\Roaming\Microsoft\Windows\Start Menu\Programs"),
    ]

    for root in roots:
        if not os.path.exists(root):
            continue
        try:
            for dirpath, _, files in os.walk(root):
                for f in files:
                    if f.lower().endswith(".lnk"):
                        full = os.path.join(dirpath, f)
                        clean = normalize_name(os.path.splitext(f)[0])
                        # Αν υπάρχουν διπλά (system + user) κρατάμε το πρώτο
                        shortcuts.setdefault(clean, full)
        except OSError:
            continue

    _start_menu_cache = shortcuts
    return shortcuts


def find_start_menu_shortcut(name):
    """Ψάχνει .lnk shortcut στο Start Menu."""
    name = normalize_name(name)
    shortcuts = _get_start_menu_shortcuts()
    if not shortcuts:
        return None

    # 1. Ακριβές match
    if name in shortcuts:
        return shortcuts[name]

    # 2. Το user query ταιριάζει σε λέξη του shortcut name
    for sc_name, path in shortcuts.items():
        if sc_name.startswith(name + " ") or name in sc_name.split():
            return path

    # 3. Partial match
    for sc_name, path in shortcuts.items():
        if name in sc_name:
            return path

    return None


# ---------------------------------------------------------------------------
# Επίπεδο 5 — App Paths registry (παρατσούκλια του "Run" dialog)
#
# Το ίδιο μέρος όπου ψάχνει το Win+R dialog. Π.χ. αν γράψεις "winword"
# στο Run, ξέρει να ανοίξει Word. Αυτό το κλειδί χαρτογραφεί exe-name -> full path.
# Πιάνει developer tools, command-line εφαρμογές, βοηθητικά προγράμματα.
# ---------------------------------------------------------------------------

_app_paths_cache = None


def _get_app_paths():
    """Διαβάζει το App Paths registry key."""
    global _app_paths_cache
    if _app_paths_cache is not None:
        return _app_paths_cache

    apps = {}
    try:
        import winreg
    except ImportError:
        _app_paths_cache = apps
        return apps

    locations = [
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE,
         r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER,
         r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    ]

    for hive, subkey_path in locations:
        try:
            with winreg.OpenKey(hive, subkey_path) as parent:
                i = 0
                while True:
                    try:
                        exe_name = winreg.EnumKey(parent, i)
                        i += 1
                    except OSError:
                        break

                    try:
                        with winreg.OpenKey(parent, exe_name) as sub:
                            # Default value είναι το full path
                            path, _ = winreg.QueryValueEx(sub, "")
                            if path:
                                path = path.strip('"').strip()
                                # Key χωρίς .exe για ευκολότερο matching
                                key_clean = normalize_name(
                                    exe_name[:-4] if exe_name.lower().endswith(".exe") else exe_name
                                )
                                apps.setdefault(key_clean, path)
                    except OSError:
                        continue
        except OSError:
            continue

    _app_paths_cache = apps
    return apps


def find_app_paths_entry(name):
    """Ψάχνει στο App Paths registry του Windows."""
    name = normalize_name(name)
    apps = _get_app_paths()
    if not apps:
        return None
    return apps.get(name)


# ---------------------------------------------------------------------------
# Fuzzy match — τελευταίο fallback
#
# Όταν ο χρήστης λέει κάτι κοντινό αλλά όχι ακριβές (π.χ. "obs" αντί για
# "OBS Studio"), συγκεντρώνουμε ΟΛΑ τα γνωστά app names από τις 4 πηγές
# και τρέχουμε string similarity. Κατώφλι 0.75 ώστε να αποφεύγουμε
# false positives (π.χ. "word" να μη γίνει "WordPad").
# ---------------------------------------------------------------------------

FUZZY_THRESHOLD = 0.7


def find_fuzzy_app(name):
    """
    Ψάχνει σε ΟΛΕΣ τις πηγές με fuzzy string matching.
    Επιστρέφει το πιο όμοιο match εφόσον περνά το κατώφλι.
    """
    name = normalize_name(name)

    # Μάζεψε όλα τα candidate names από όλες τις πηγές
    candidates = {}  # { app_name: launchable_path }

    for k, v in _get_installed_apps().items():
        candidates.setdefault(k, v)

    for k, v in _get_start_menu_shortcuts().items():
        candidates.setdefault(k, v)

    for k, v in _get_app_paths().items():
        candidates.setdefault(k, v)

    for k, v in _get_uwp_apps().items():
        # τα UWP θέλουν το "uwp:" πρόθεμα ώστε να τα ανοίξει σωστά το launch_path
        candidates.setdefault(k, f"uwp:{v}")

    if not candidates:
        return None

    # difflib.get_close_matches βρίσκει τα πιο όμοια κλειδιά
    matches = difflib.get_close_matches(
        name, candidates.keys(), n=1, cutoff=FUZZY_THRESHOLD
    )
    if matches:
        return candidates[matches[0]]
    return None


# ---------------------------------------------------------------------------
# Λογική εύρεσης
# ---------------------------------------------------------------------------

def find_known_path(name, search_type):
    """Δοκιμάζει πρώτα τους γνωστούς apps/φακέλους — άμεσο, χωρίς walk."""
    if name not in KNOWN_OPEN_APPS:
        return None

    for path in KNOWN_OPEN_APPS[name]:
        if search_type == "folder":
            if os.path.exists(path) and os.path.isdir(path):
                return path
            continue

        # Protocol URIs ("ms-settings:") "υπάρχουν" πάντα — τα χειρίζονται
        # τα Windows. Ομοίως και τα exe από το PATH.
        if path.endswith(":"):
            return path

        if path.endswith(".exe") or path.endswith(".msc"):
            if os.path.exists(path) or not os.path.isabs(path):
                return path

        if os.path.exists(path):
            return path

    return None


def should_skip_folder(root):
    """Φάκελοι που είναι θόρυβος — δεν μας ενδιαφέρει τίποτα μέσα τους."""
    root_lower = root.lower()
    skipped = [
        "$recycle.bin",
        "system volume information",
        "node_modules",
        "__pycache__",
        ".git",
        ".venv",
        "venv",
    ]
    return any(x in root_lower for x in skipped)


def find_path(name, search_type="any"):
    """
    Έξυπνη αναζήτηση για apps, φακέλους ή αρχεία.

    search_type:
    - "app"
    - "folder"
    - "file"
    - "any"

    Στρατηγική (από φθηνότερο σε ακριβότερο):
      1. Cache hit
      2. KNOWN_OPEN_APPS lookup
      3. Walk στους SEARCH_DIRS με όριο βάθους
    """
    name = normalize_name(name)
    cache_key = f"{search_type}:{name}"
    cache = load_cache()

    # 1. Cache hit
    cached = cache.get(cache_key)
    if cached:
        # τα UWP entries δεν έχουν filesystem path, οπότε δεν
        # μπορούμε να κάνουμε os.path.exists. Τα δεχόμαστε όπως είναι.
        if cached.startswith("uwp:"):
            return cached
        if os.path.exists(cached):
            return cached

    # 2. Γνωστά apps/φάκελοι
    if search_type in ["app", "folder", "any"]:
        known = find_known_path(name, search_type if search_type != "any" else "app")
        if known:
            if os.path.exists(known):
                cache[cache_key] = known
                save_cache(cache)
            return known

        # Αν το "any" δεν βρήκε ως app, δοκίμασε και ως φάκελο
        if search_type == "any":
            known_folder = find_known_path(name, "folder")
            if known_folder:
                cache[cache_key] = known_folder
                save_cache(cache)
                return known_folder

    # 2β. UWP / Microsoft Store apps (Netflix, Spotify Store, Disney+, κ.λπ.)
    # Δοκιμάζεται ΠΡΙΝ το αργό os.walk γιατί είναι πολύ πιο γρήγορο
    # (~1 sec την πρώτη φορά, ακαριαίο από εκεί και μετά λόγω cache).
    # Πιάνει εφαρμογές που δεν είναι κανονικά .exe και ΔΕΝ θα τις έβρισκε
    # ποτέ το os.walk.
    if search_type in ["app", "any"]:
        uwp_path = find_uwp_app(name)
        if uwp_path:
            cache[cache_key] = uwp_path
            save_cache(cache)
            return uwp_path

    # 2γ. Windows Registry — εγκατεστημένα προγράμματα.
    # Πιάνει το ~90% των non-Store εφαρμογών (Discord, Zoom, VLC, OBS, GIMP,
    # παιχνίδια, κ.λπ.) χωρίς να σαρώνουμε τον δίσκο.
    if search_type in ["app", "any"]:
        installed = find_installed_app(name)
        if installed:
            cache[cache_key] = installed
            save_cache(cache)
            return installed

    # 2δ. Start Menu shortcuts (.lnk αρχεία).
    # Πιάνει ό,τι έχει shortcut στο Start Menu — δηλαδή ουσιαστικά όλα όσα
    # βλέπει ο χρήστης όταν πατάει το πλήκτρο Windows.
    if search_type in ["app", "any"]:
        sc = find_start_menu_shortcut(name)
        if sc:
            cache[cache_key] = sc
            save_cache(cache)
            return sc

    # 2ε. App Paths registry — ό,τι ανοίγει με Win+R.
    # Πιάνει developer tools και command-line εφαρμογές.
    if search_type in ["app", "any"]:
        ap = find_app_paths_entry(name)
        if ap:
            cache[cache_key] = ap
            save_cache(cache)
            return ap

    # 3. Fuzzy / partial αναζήτηση στον δίσκο
    # Αρχικοποιούμε εδώ για να μην έχουμε ΠΟΤΕ UnboundLocalError παρακάτω.
    best_app = None
    best_folder = None
    best_file = None

    for base in SEARCH_DIRS:
        if not os.path.exists(base):
            continue

        # Χρησιμοποιείται για να υπολογίσουμε το current depth
        base_depth = base.count(os.sep)

        for root, dirs, files in os.walk(base):
            # Όριο βάθους — δεν κατεβαίνουμε πέρα από
            # MAX_WALK_DEPTH επίπεδα από τη βάση.
            current_depth = root.count(os.sep) - base_depth
            if current_depth >= MAX_WALK_DEPTH:
                dirs[:] = []  # σταματάμε το descent
                continue

            # Όταν θέλουμε να σκιπάρουμε έναν φάκελο, πρέπει να
            # κάνουμε ΚΑΙ dirs[:] = [] αλλιώς το os.walk θα κατέβει
            # στα subfolders του (π.χ. στο $Recycle.bin\xxxxx).
            if should_skip_folder(root):
                dirs[:] = []
                continue

            # Αναζήτηση φακέλων
            if search_type in ["folder", "any"]:
                for folder in dirs:
                    clean_folder = normalize_name(folder)
                    path = os.path.join(root, folder)

                    # Ακριβές match — επιστρέφουμε αμέσως
                    if name == clean_folder:
                        cache[cache_key] = path
                        save_cache(cache)
                        return path

                    # "downloads folder" → "downloads"
                    if name.endswith(" folder"):
                        no_folder = name.replace(" folder", "").strip()
                        if no_folder == clean_folder:
                            cache[cache_key] = path
                            save_cache(cache)
                            return path

                    # Μερικό match — το θυμόμαστε αλλά συνεχίζουμε
                    if clean_folder.startswith(name) or name.startswith(clean_folder):
                        best_folder = path

            # Αναζήτηση αρχείων / app
            if search_type in ["app", "file", "any"]:
                for file in files:
                    file_lower = file.lower()
                    file_no_ext = normalize_name(os.path.splitext(file_lower)[0])
                    path = os.path.join(root, file)

                    is_app = file_lower.endswith(APP_EXTENSIONS)
                    is_file = file_lower.endswith(FILE_EXTENSIONS)

                    # Φιλτράρουμε με βάση το search_type
                    if search_type == "app" and not is_app:
                        continue
                    if search_type == "file" and not is_file:
                        continue
                    if search_type == "any" and not (is_app or is_file):
                        continue

                    # Ακριβές match
                    if name == file_no_ext:
                        cache[cache_key] = path
                        save_cache(cache)
                        return path

                    # Μερικό match
                    if name in file_no_ext:
                        if is_app:
                            best_app = path
                        else:
                            best_file = path

    # Πέφτουμε στο καλύτερο μερικό match
    if search_type == "folder":
        result = best_folder
    elif search_type == "app":
        result = best_app
    elif search_type == "file":
        result = best_file
    else:
        # "any" — προτεραιότητα: app > folder > file
        result = best_app or best_folder or best_file

    if result:
        cache[cache_key] = result
        save_cache(cache)
        return result

    # 4. Τελευταίο fallback — fuzzy match σε όλες τις πηγές apps.
    # Π.χ. ο χρήστης είπε "obs" αλλά εγκατεστημένο είναι "OBS Studio",
    # ή "discord" αλλά είναι "Discord PTB". Με κατώφλι FUZZY_THRESHOLD
    # αποφεύγουμε ξεκάθαρα λάθος matches.
    if search_type in ["app", "any"]:
        fuzzy = find_fuzzy_app(name)
        if fuzzy:
            cache[cache_key] = fuzzy
            save_cache(cache)
            return fuzzy

    return None


# ---------------------------------------------------------------------------
# Κλείσιμο εφαρμογών
# ---------------------------------------------------------------------------

def close_app(app_name):
    """
    Κλείνει εφαρμογή με βάση το όνομα της διεργασίας.
    Δεν μιλάει εδώ — το executor.py αναλαμβάνει όλες τις φωνητικές απαντήσεις.
    """
    known_processes = {
        "spotify": "Spotify.exe",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "discord": "Discord.exe",
        "steam": "steam.exe",
        "notepad": "notepad.exe",
        "word": "WINWORD.EXE",
        "excel": "EXCEL.EXE",
        "powerpoint": "POWERPNT.EXE",
        "vs code": "Code.exe",
        "code": "Code.exe",
        "epic": "EpicGamesLauncher.exe",
        "minecraft": "MinecraftLauncher.exe",
        "valorant": "VALORANT-Win64-Shipping.exe",
        "league": "LeagueClient.exe",
        "league of legends": "LeagueClient.exe",
        "riot": "RiotClientServices.exe",
    }

    app_name = app_name.lower().strip()

    # Ψάχνουμε πρώτα στα γνωστά process names
    for key, exe in known_processes.items():
        if key in app_name:
            subprocess.call(f'taskkill /f /im "{exe}"', shell=True)
            return

    # Έσχατη λύση: υποθέτουμε ότι "spotify" → "spotify.exe"
    subprocess.call(f'taskkill /f /im "{app_name}.exe"', shell=True)


# ---------------------------------------------------------------------------
# Web helpers
# ---------------------------------------------------------------------------

def open_google_search(query):
    """Ανοίγει Google search στον default browser."""
    # quote_plus encodes σωστά τα κενά και τους ειδικούς χαρακτήρες για URL
    encoded = urllib.parse.quote_plus(query)
    subprocess.call(f'start https://www.google.com/search?q={encoded}', shell=True)


def open_youtube_search(query):
    """Ανοίγει YouTube search στον default browser."""
    encoded = urllib.parse.quote_plus(query)
    subprocess.call(
        f'start https://www.youtube.com/results?search_query={encoded}',
        shell=True
    )