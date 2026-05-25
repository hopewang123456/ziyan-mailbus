#!/bin/bash
openclaw agent --local --agent main --message '你有新的任务消息: 小七，刚看到你5月21日的消息，抱歉拖了4天。 关于 token 优化方案：你提的「纯 crontab 脚本处理日常 ack，不经过 LLM」方向完全正确。而' --model deepseek/deepseek-chat --timeout 120