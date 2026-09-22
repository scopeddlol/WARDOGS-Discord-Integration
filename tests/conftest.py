import os
from pathlib import Path
import tempfile

# Tests must never touch the user's real settings or runtime message state.
os.environ['WARDOGS_DATA_DIR'] = tempfile.mkdtemp(prefix='wardogs-tests-')
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
