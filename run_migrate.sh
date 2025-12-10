#!/bin/bash
cd /opt/waifu-bot-REBORN
export PYTHONPATH=/opt/waifu-bot-REBORN/src:$PYTHONPATH
.venv/bin/python -c "from alembic.config import main; main(['upgrade', 'head'])"

