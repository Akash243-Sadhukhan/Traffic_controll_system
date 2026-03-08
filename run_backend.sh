#!/usr/bin/env bash
set -euo pipefail
# Build and run the Spring Boot application using the Maven wrapper
cd "$(dirname "$0")"
./mvnw -DskipTests clean package
exec java -jar target/backend-services-0.0.1-SNAPSHOT.jar
