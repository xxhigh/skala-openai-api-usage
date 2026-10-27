
import os
import hmac
import hashlib
import time
import httpx

from fastapi import FastAPI, Request, HTTPException

app = FastAPI()

USAGE_URL = os.environ["USAGE_DATA_URL"]
SLACK_SECRET = os.environ["SLACK_SIGNING_SECRET"]


@app.get("/")
def health():
    return {"status": "ok"}


@app.post("/slack/usage")
async def usage(request: Request):
    body = await request.body()

    # Slack 요청 서명 검증
    timestamp = request.headers.get(
        "X-Slack-Request-Timestamp", ""
    )
    signature = request.headers.get(
        "X-Slack-Signature", ""
    )

    if not timestamp.isdigit():
        raise HTTPException(status_code=401)

    if abs(time.time() - int(timestamp)) > 300:
        raise HTTPException(status_code=401)

    message = b"v0:" + timestamp.encode() + b":" + body

    expected = "v0=" + hmac.new(
        SLACK_SECRET.encode(),
        message,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401)

    # 사용량 조회
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            response = await client.get(USAGE_URL)
            response.raise_for_status()
            data = response.json()

        if not data.get("ok") or not data.get("cost_available"):
            raise ValueError("Usage data unavailable")

        spent = float(data["spent_usd"])
        remaining = float(data["remaining_usd"])
        today = float(data["today_spent_usd"])
        limit = float(data["limit_usd"])
        percent = float(data["percent_used"])

        text = (
            "*OpenAI API 사용량 현황*\n\n"
            f"남은 금액: `${remaining:.2f}`\n"
            f"누적 사용액: `${spent:.2f}`\n"
            f"오늘 사용액: `${today:.2f}`\n"
            f"전체 한도: `${limit:.2f}`\n"
            f"사용률: `{percent:.1f}%`\n\n"
            f"최종 갱신: {data['updated_at']}"
        )

    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        text = "사용량 데이터를 불러오지 못했습니다."

    return {
        "response_type": "ephemeral",
        "text": text
    }
