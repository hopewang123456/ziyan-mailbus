FROM python:3.12-slim

# 复制 docker CLI 二进制
COPY docker /usr/local/bin/docker

RUN pip install --no-cache-dir PyYAML

WORKDIR /mailbus

EXPOSE 9814

CMD ["python3", "-m", "bus", "serve", "--host", "0.0.0.0", "--port", "9814"]
