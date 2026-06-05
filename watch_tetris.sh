#!/bin/bash
caffeinate -i &
docker logs -f trading_bot_main 2>&1 | grep --line-buffered -E "=== Cycle|SIGNAL:|Exit|Error|square|Token valid"
