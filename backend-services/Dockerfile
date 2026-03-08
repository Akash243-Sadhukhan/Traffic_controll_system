FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /app

# 1. Copy only pom.xml and download dependencies (this layer is cached)
COPY pom.xml .
RUN mvn dependency:go-offline

# 2. Now copy the source and build
COPY src ./src
RUN mvn clean package -DskipTests

# Stage 2: Final Image
FROM eclipse-temurin:21-jre-jammy
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.jar"]