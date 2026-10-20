ARG BUILD_FROM
FROM $BUILD_FROM
# Alpine's packaged Pillow avoids compiling image libraries on the Green.
RUN apk add --no-cache python3 py3-pillow
COPY app /app
CMD ["python3", "-u", "/app/server.py"]
