#!/usr/bin/env python3
"""Run alembic migrations."""
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.venv', 'lib', 'python3.12', 'site-packages'))

# Set environment
os.environ.setdefault('PYTHONPATH', ':'.join(sys.path))

from alembic import command
from alembic.config import Config

if __name__ == '__main__':
    alembic_cfg = Config('alembic.ini')
    command.upgrade(alembic_cfg, 'head')

