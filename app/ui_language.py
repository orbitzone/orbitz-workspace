"""Load translations bundled with this standalone application."""
import os
from pathlib import Path
import sys
_root = Path(os.environ.get('ORBITZ_I18N_DIR', Path(__file__).resolve().parents[1] / 'i18n'))
sys.path.insert(0, str(_root))
import ui_i18n as ui
