# 원격(HTTP) MCP 서버용. 로컬 stdio 사용엔 필요 없다.
#   docker build -t budongsan-tax . && docker run -p 8000:8000 budongsan-tax
# 엔드포인트: http://<host>:8000/mcp  (인증 없음 — 공개 배포 시 앞단 프록시에서 처리)
FROM python:3.12-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir .
ENV MCP_TRANSPORT=streamable-http HOST=0.0.0.0 PORT=8000 MCP_PATH=/mcp
EXPOSE 8000
CMD ["budongsan-tax"]
