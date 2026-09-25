# syntax=docker/dockerfile:1
# Сборка из корня репозитория: docker build -f backend/Dockerfile .
# В образ попадают только jar и артефакты модели, сырых данных и Python в нём нет.

FROM eclipse-temurin:25-jdk AS build
WORKDIR /src
COPY backend/gradlew backend/settings.gradle.kts backend/build.gradle.kts ./
COPY backend/gradle ./gradle
RUN chmod +x gradlew
# зависимости отдельным слоем: при правке кода они не скачиваются заново
RUN --mount=type=cache,target=/root/.gradle ./gradlew --no-daemon -q dependencies > /dev/null
COPY backend/src ./src
RUN --mount=type=cache,target=/root/.gradle ./gradlew --no-daemon -q bootJar \
    && java -Djarmode=tools -jar build/libs/app.jar extract --layers --launcher --destination /extracted

FROM eclipse-temurin:25-jre
RUN groupadd --system app && useradd --system --gid app --uid 10001 app
WORKDIR /app
COPY --from=build /extracted/dependencies/ ./
COPY --from=build /extracted/spring-boot-loader/ ./
COPY --from=build /extracted/snapshot-dependencies/ ./
COPY --from=build /extracted/application/ ./
COPY artifacts/manifest.json artifacts/coefficients.json artifacts/intervals.json artifacts/backtest_metrics.json \
     artifacts/forecast_components.csv artifacts/forecast_year.csv artifacts/stops.csv artifacts/route_stops.csv \
     artifacts/network.geojson /app/artifacts/
ENV TRAMLOAD_ARTIFACTS_DIR=/app/artifacts \
    JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=70 -XX:+ExitOnOutOfMemoryError"
USER app
EXPOSE 8080
# curl и wget в образе JRE нет, проверяем готовность через bash и /dev/tcp
HEALTHCHECK --interval=5s --timeout=3s --start-period=15s --retries=10 \
    CMD ["bash", "-c", "exec 3<>/dev/tcp/127.0.0.1/8080 && printf 'GET /actuator/health/readiness HTTP/1.0\\r\\n\\r\\n' >&3 && grep -q '\"UP\"' <&3"]
ENTRYPOINT ["java", "org.springframework.boot.loader.launch.JarLauncher"]
