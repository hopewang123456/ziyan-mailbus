FROM python:3.12-slim

# 不安装 docker CLI：mailbus 不控制 Docker（投递走 A2A / file_bus），
# 也不再挂载 /var/run/docker.sock —— 见 tests/guards 的部署形态守卫。

# 运行依赖由镜像提供；源码经 ../..:/mailbus 挂载
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30"

WORKDIR /mailbus/python

EXPOSE 9814

CMD ["python3", "-m", "uvicorn", "mailbus.bootstrap.main:app", "--host", "0.0.0.0", "--port", "9814"]
