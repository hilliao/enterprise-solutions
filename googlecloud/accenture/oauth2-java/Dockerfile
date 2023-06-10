# Docker multi-stage build
FROM gradle:jdk11 AS build
COPY --chown=gradle:gradle . /home/gradle/workspace
WORKDIR /home/gradle/workspace
RUN gradle build -x test --no-daemon

# packaging stage
FROM openjdk:11
WORKDIR /app
COPY --from=build /home/gradle/workspace/build/libs/*.jar app.jar
RUN mkdir /opt/cdbg && \
     wget -qO- https://storage.googleapis.com/cloud-debugger/compute-java/debian-wheezy/cdbg_java_agent_gce.tar.gz | \
     tar xvz -C /opt/cdbg
ENTRYPOINT ["java", "-agentpath:/opt/cdbg/cdbg_java_agent.so", "-Dcom.google.cdbg.breakpoints.enable_canary=true", \
            "-Djava.security.egd=file:/dev/./urandom", "-Dserver.port=${PORT}", "-jar", "app.jar"]