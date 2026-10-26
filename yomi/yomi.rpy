# Yomi - hover dictionary for Ren'Py games.
#
# Hold Shift and point at Japanese text to see a dictionary card.
# Scroll the card with the mouse wheel; Esc or moving away closes it.
#
# Settings: uncomment and change the lines below.

init 999 python:

    # The mod's folder inside game/, and its log file there.
    _yomi_directory = "yomi"
    _yomi_log_file = "yomi_log.txt"

    def _yomi_setup():
        import os
        import sys

        path = os.path.join(config.gamedir, _yomi_directory)
        if path not in sys.path:
            sys.path.insert(0, path)

        import yomi_renpy
        settings = yomi_renpy.config

        # Key to hold while pointing: "shift", "alt", "ctrl" or "always".
        # settings.key = "shift"

        # Card size multiplier.
        # settings.scale = 1.0

        # Card width (fraction of the screen width).
        # settings.width = 0.46

        # Write each lookup to yomi/yomi_log.txt (errors are always written).
        # settings.debug = True

        yomi_renpy.install()

    # A broken mod must never stop the game from starting.
    try:
        _yomi_setup()
    except Exception:
        import os as _yomi_os
        import traceback as _yomi_traceback
        try:
            _yomi_path = _yomi_os.path.join(config.gamedir, _yomi_directory, _yomi_log_file)
            with open(_yomi_path, "a") as _yomi_file:
                _yomi_file.write("Yomi failed to load:\n" + _yomi_traceback.format_exc())
        except Exception:
            pass
