# 迁移后验收

- [ ] `pip install -e mail`
- [ ] `mailbus migrate plan` — required 路径均 exists
- [ ] `mailbus doctor` — 无 FAIL（Docker 可选 WARN）
- [ ] `mailbus compose sync` — override 已生成
- [ ] `mailbus start` — 容器 up
- [ ] `mailbus smoke` — 冒烟通过
- [ ] （WSL systemd）`sudo bash docker-agents/install-mailbus-watchdog-service.sh`
