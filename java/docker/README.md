# mailbus-j container

Build (after `mvn -pl mailbus-boot -am package -DskipTests` in java/):

```bash
docker build -t mailbus-j:0.1.0 -f docker/Dockerfile .
docker run -d --name mailbus-j -p 9815:9815 -v <your-store>:/app/store mailbus-j:0.1.0
```

Or via compose: `docker compose -f docker/docker-compose.yml up -d`

- Serve mode by default on :9815 (9814 stays with the python serve — dual-run friendly).
- CLI: `docker exec mailbus-j java -jar /app/app.jar agents`
- Health: `curl http://127.0.0.1:9815/actuator/health`
