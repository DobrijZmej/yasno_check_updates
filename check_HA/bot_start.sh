#!/bin/bash
cd /apps/electricity/check_HA/
date >> bot.log
python3.10 main.py --cron 1>> bot.log 
#2>>bot_errors.log