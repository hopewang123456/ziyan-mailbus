# mailbus-j runtime image (M4 deliverable).
# Build from the java/ directory after `mvn -pl mailbus-boot -am package -DskipTests`:
#   docker build -t mailbus-j:0.1.0 -f docker/Dockerfile .
# BASE overridable for constrained networks:
#   docker build --build-arg BASE=docker.m.daocloud.io/library/eclipse-temurin:25-jre-jammy ...
ARG BASE=eclipse-temurin:25-jre-jammy
FROM ${BASE}

WORKDIR /app
COPY mailbus-boot/target/mailbus-boot-0.1.0-SNAPSHOT.jar app.jar

# store volume: messages (files) + metadata.db live here
VOLUME ["/app/store"]
EXPOSE 9815

# serve mode by default; CLI subcommands work too:
#   docker run --rm mailbus-j:0.1.0 agents
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
