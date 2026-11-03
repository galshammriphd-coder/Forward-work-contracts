import os
import sys
import tempfile
import warnings
from pathlib import Path

os.environ.setdefault("RA_DATA_DIR", tempfile.mkdtemp(prefix="ra_test_"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")
