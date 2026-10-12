"""Locate durable user data independently of bundled application resources."""
import os
from pathlib import Path
import sys

def user_data_dir(source_root):
    if not getattr(sys, 'frozen', False) and os.environ.get('QC_DESKTOP_PACKAGED') != '1':
        return Path(source_root)
    return Path(os.environ.get('LOCALAPPDATA') or Path.home()) / 'QC_ESP32'
