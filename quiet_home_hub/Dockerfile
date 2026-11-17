ARG BUILD_FROM
FROM $BUILD_FROM
# Alpine's packaged Pillow avoids compiling image libraries on the Green; ffmpeg makes
# the 4K photo videos for the TV's video layer.
RUN apk add --no-cache python3 py3-pillow ffmpeg
COPY app /app
# s6-overlay starts CMD with a clean environment; with-contenv restores SUPERVISOR_TOKEN.
CMD ["with-contenv", "python3", "-u", "/app/server.py"]
