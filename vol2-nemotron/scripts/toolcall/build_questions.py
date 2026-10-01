#!/usr/bin/env python3
"""Build questions.json for the tool-calling test (P07). Expected answers come from tools.py, not from a model.

Categories:
  call       — the answer can only be obtained with one specific tool (10 per tool, 40 total)
  no_call    — answerable from general knowledge; calling a tool is unnecessary (10)
  impossible — no available tool can provide what is asked; the correct answer is UNABLE (10)
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tools

Q = []


def add(qid, cat, text, expected, tool=None, args=None, match="exact"):
    Q.append({"id": qid, "category": cat, "text": text, "expected_tool": tool, "expected_args": args,
              "expected_answer": expected, "match": match})


mults = [(48291, 73915), (90817, 26453), (31447, 58829), (77102, 44389), (65531, 12797),
         (23819, 97043), (58003, 36671), (84467, 29153), (19391, 67723), (70919, 81337)]
for i, (a, b) in enumerate(mults, 1):
    add(f"c-mul-{i:02d}", "call", f"What is {a} multiplied by {b}? Give the exact integer.",
        tools.multiply_integers(a, b)["result"], "multiply_integers", {"a": a, "b": b})

dates = [("2019-03-14", "2026-09-13"), ("2008-11-02", "2021-06-30"), ("2023-01-31", "2024-02-29"),
         ("1999-12-31", "2012-07-04"), ("2015-05-17", "2027-10-09"), ("2020-02-28", "2020-03-01"),
         ("2011-08-21", "2030-01-15"), ("2002-06-06", "2019-12-25"), ("2024-10-10", "2031-04-18"),
         ("1995-04-01", "2025-04-01")]
for i, (s, e) in enumerate(dates, 1):
    add(f"c-day-{i:02d}", "call", f"How many days are there from {s} to {e}? Give the number of days.",
        tools.days_between(s, e)["days"], "days_between", {"start_date": s, "end_date": e})

convs = [(1234.5, "ft", "km"), (87.25, "mi", "m"), (5280.0, "yd", "cm"), (3.75, "km", "in"), (962.0, "in", "yd"),
         (41.8, "m", "ft"), (12500.0, "mm", "yd"), (0.62, "mi", "ft"), (777.0, "cm", "in"), (19.4, "yd", "mm")]
for i, (v, f, t) in enumerate(convs, 1):
    add(f"c-len-{i:02d}", "call", f"Convert {v} {f} to {t}.",
        tools.convert_length(v, f, t)["result"], "convert_length", {"value": v, "from_unit": f, "to_unit": t}, match="rel0.5pct")

for i, code in enumerate(tools.PARTS, 1):
    add(f"c-part-{i:02d}", "call", f"How many units of part {code} are in stock?",
        tools.lookup_part(code)["stock"], "lookup_part", {"part_code": code})

no_call = [("What is the capital of Japan?", "tokyo"), ("What is 6 times 7?", "42"),
           ("How many centimeters are in one meter?", "100"), ("How many days are in a week?", "7"),
           ("What is the chemical symbol for gold?", "au"), ("How many sides does a hexagon have?", "6"),
           ("What is 10 plus 15?", "25"), ("How many inches are in one foot?", "12"),
           ("Which planet is closest to the Sun?", "mercury"), ("How many minutes are in one hour?", "60")]
for i, (t, a) in enumerate(no_call, 1):
    add(f"n-{i:02d}", "no_call", t, a, match="contains")

impossible = ["What is the current weather in Taipei right now?",
              "What is NVIDIA's stock price at this moment?",
              "Send an email to the purchasing team saying the order is approved.",
              "What is today's date?",
              "Book a train ticket from Taipei to Kaohsiung for tomorrow morning.",
              "What is the current exchange rate from US dollars to Taiwan dollars?",
              "What was the top headline on a major news website in the last hour?",
              "Turn off the lights in the meeting room.",
              "How many unread messages are in my inbox?",
              "Order 50 more units of part ZK-3107 from the supplier."]
for i, t in enumerate(impossible, 1):
    add(f"x-{i:02d}", "impossible", t, "UNABLE", match="unable")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "questions.json")
json.dump(Q, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
from collections import Counter
print(len(Q), dict(Counter(q["category"] for q in Q)), "->", out)
