
import json
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(title="The Ledger Agent")

DATA_URL = "https://exam.sanand.workers.dev/questionData?email=23f2005438%40ds.study.iitm.ac.in&quizSign=yA0PXNSgsn2NmKka04ayxJhhCNWR0Ulw096cpSz5Pnwbs2I7XlT%2FZgAv8gW3kt6yjLBqZJjvX9rNa9tBDI08m2kbVC%2BITEp2zmAB9hml%2FiAdwp2pG4JcHr9PKze553FdRTID5usKKWabZECkJqgyBviEmZgXWRfTU%2F4aiBnWLjHdhyi1WBp8ds6zU6Q%2FoniK0qCRjoRuR7X9g413DMkTVPJ2%2Ff%2BrW7ILBkn9Ja2mh44jlutJ12J%2F4DDC3AWEB%2BCaIjZBN3CM%2Bfrb8JNd0MkGmrmYNrxmQbLkfy2%2By17pKIFz72JiXl%2FKztAH%2BLuaWThC42VzQyVtlylcY3iOkLKOrg%3D%3D&questionId=q-ledger-agent-server&path=%2Frates"

with open("export.txt", "r") as f:
    orders = [json.loads(line) for line in f if line.strip()]

rates_response = requests.get(DATA_URL, timeout=30)
rates_response.raise_for_status()
rates = rates_response.json()["usd_per_unit"]

# Keep the latest version of each order.
latest = {}
for order in orders:
    oid = order["id"]
    if oid not in latest or datetime.fromisoformat(
        order["updated_at"].replace("Z", "+00:00")
    ) > datetime.fromisoformat(
        latest[oid]["updated_at"].replace("Z", "+00:00")
    ):
        latest[oid] = order

orders = list(latest.values())


class Question(BaseModel):
    question: str


def answer_question(question: str):
    q = question.lower()
    selected = orders[:]

    # Filter by region.
    for region in ["north", "south", "east", "west", "central"]:
        if region in q and re.search(r"\b(region|from|in|for)\b", q):
            selected = [
                o for o in selected if o["region"].lower() == region
            ]
            break

    # Filter by product.
    for product in sorted(
        {o["product"] for o in orders}, key=len, reverse=True
    ):
        if product.lower() in q:
            selected = [
                o for o in selected
                if o["product"].lower() == product.lower()
            ]
            break

    # Filter by date range, using the business timezone.
    months = {
        "january": 1, "february": 2, "march": 3,
        "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9,
        "october": 10, "november": 11, "december": 12,
    }
    date_match = re.search(
        r"\b(" + "|".join(months) + r")\s+(20\d{2})\b", q
    )
    if date_match:
        month = months[date_match.group(1)]
        year = int(date_match.group(2))
        selected = [
            o for o in selected
            if (lambda d: d.year == year and d.month == month)(
                datetime.fromisoformat(
                    o["created_at"].replace("Z", "+00:00")
                ).astimezone(ZoneInfo("Asia/Kolkata"))
            )
        ]

    # Filter by status if requested.
    for status in ["paid", "refunded", "void"]:
        if status in q and (
            "status" in q or "orders" in q or "count" in q
        ):
            selected = [o for o in selected if o["status"] == status]
            break

    # Revenue includes only paid orders.
    if "revenue" in q or "sales" in q or "total" in q:
        selected = [o for o in selected if o["status"] == "paid"]
        usd_total = sum(
            float(o.get("amount", float(o["unit_price"]) * int(o["qty"])))
            * rates.get(o["currency"], 0)
            for o in selected
        )
        return {"answer": round(usd_total, 2)}

    if "count" in q or "how many" in q or "number of" in q:
        return {"answer": len(selected)}

    if "customer" in q:
        return {"answer": len({o["customer"] for o in selected})}

    if "quantity" in q or "units" in q:
        return {"answer": sum(int(o["qty"]) for o in selected)}

    return {
        "answer": (
            "Please ask about revenue, order count, customers, or units, "
            "and include any relevant region, product, or month."
        )
    }


@app.get("/")
def home():
    return {"message": "Ledger Agent is running"}


@app.post("/")
def ask_question(body: Question):
    return answer_question(body.question)

