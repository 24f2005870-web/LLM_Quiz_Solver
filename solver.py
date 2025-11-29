# solver.py
import os
import re
import time
import json
import base64
import logging
import requests
import asyncio
from urllib.parse import urljoin
from playwright.async_api import async_playwright, TimeoutError as PWTimeout

logger = logging.getLogger("quiz-solver")
logger.setLevel(logging.INFO)

# helper libs for parsing
try:
    import pandas as pd
except Exception:
    pd = None

try:
    import pdfplumber
except Exception:
    pdfplumber = None

class QuizSolver:
    def __init__(self, email: str, secret: str, max_seconds: int = 180):
        self.email = email
        self.secret = secret
        self.max_seconds = max_seconds

    async def process_quiz_url(self, start_url: str, original_payload: dict):
        start_time = time.time()
        deadline = start_time + self.max_seconds
        current_url = start_url
        session_payload = original_payload.copy()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            while time.time() < deadline and current_url:
                remaining = int(deadline - time.time())
                logger.info(f"Visiting {current_url} (time left: {remaining}s)")
                try:
                    await page.goto(current_url, timeout=60000)
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except PWTimeout:
                    logger.warning("Timeout waiting for page; continuing with what we have")

                # Extract visible text and raw HTML
                try:
                    visible_text = await page.inner_text("body")
                except Exception:
                    visible_text = ""
                html = await page.content()

                # Find submit URL
                submit_url = self.find_submit_url(page, html, current_url)
                if not submit_url:
                    # Fallback scanning of visible text
                    m = re.search(r"https?://[^\s'\"<>]+/submit[^\s'\"<>]*", visible_text)
                    submit_url = m.group(0) if m else None

                # Determine answer using heuristics
                answer = await self.solve_from_page(page, html, visible_text, current_url, remaining)

                if not submit_url:
                    logger.info("No submit URL found; returning debug payload")
                    # not ideal; end loop
                    return {"status": "no_submit", "url": current_url, "answer_candidate": answer}

                # Build submission payload
                submission = {
                    "email": self.email,
                    "secret": self.secret,
                    "url": current_url,
                    "answer": answer
                }

                logger.info(f"Submitting answer to {submit_url}: payload keys={list(submission.keys())}")
                try:
                    resp = requests.post(submit_url, json=submission, timeout=min(30, max(5, remaining-1)))
                except Exception as e:
                    logger.exception("Error posting answer")
                    return {"status": "submit_error", "reason": str(e)}

                try:
                    resp_json = resp.json()
                except Exception:
                    resp_json = {"status": resp.status_code, "text": resp.text}

                logger.info(f"Submit response: {resp_json}")

                # If correct and there's a next URL, follow it
                if isinstance(resp_json, dict) and resp_json.get("correct") is True:
                    next_url = resp_json.get("url")
                    if not next_url:
                        # finished
                        await browser.close()
                        return {"status": "finished", "last_response": resp_json}
                    else:
                        current_url = next_url
                        # continue loop
                        continue
                else:
                    # If incorrect, maybe get next_url or retry
                    next_url = resp_json.get("url") if isinstance(resp_json, dict) else None
                    if next_url:
                        current_url = next_url
                        continue
                    else:
                        # Optionally retry until deadline
                        logger.info("Answer incorrect and no next URL; finishing with response")
                        await browser.close()
                        return {"status": "incorrect", "last_response": resp_json}

            await browser.close()
            return {"status": "timeout_or_deadline"}

    def find_submit_url(self, page, html, base_url):
        # Attempt to find form action or script-embedded submit URL
        try:
            forms = page.query_selector_all("form")
            for f in forms:
                action = f.get_attribute("action")
                method = (f.get_attribute("method") or "GET").upper()
                if action and method == "POST":
                    return urljoin(base_url, action)
        except Exception:
            pass

        # Search for common patterns in HTML
        m = re.search(r'https?://[^\s"\'<>]+/submit[^\s"\'<>]*', html)
        if m:
            return m.group(0)
        return None

    async def solve_from_page(self, page, html, visible_text, page_url, time_left):
        """
        Heuristic solver:
        - If there's a direct instruction like "Download file. What is the sum..."
          try to find download links, fetch file, parse CSV/XLSX/PDF.
        - Fallbacks: if visible_text asks for boolean or trivial answer, try to infer.
        - Final fallback: return a short text snippet.
        """
        # Quick heuristics
        # 1) Look for download link to csv/xlsx/pdf
        try:
            anchors = page.query_selector_all("a")
            file_link = None
            for a in anchors:
                href = a.get_attribute("href") or ""
                href_low = href.lower()
                if any(ext in href_low for ext in [".csv", ".xlsx", ".xls", ".pdf"]):
                    file_link = href if href.startswith("http") else urljoin(page_url, href)
                    break
        except Exception:
            file_link = None

        if file_link:
            logger.info(f"Found file link: {file_link}")
            try:
                r = requests.get(file_link, timeout=min(30, max(10, time_left-1)))
                content = r.content
                ct = r.headers.get("content-type", "")
                # Try CSV
                if (ct and "text/csv" in ct) or b"," in content[:2000]:
                    if pd is None:
                        logger.warning("pandas not installed; cannot parse CSV")
                    else:
                        from io import BytesIO
                        try:
                            df = pd.read_csv(BytesIO(content))
                            # try sum of column named 'value' (case-insensitive)
                            for col in df.columns:
                                if col.strip().lower() == "value":
                                    s = df[col].sum()
                                    try:
                                        return float(s)
                                    except:
                                        return s
                        except Exception as e:
                            logger.exception("CSV parse failed")
                # Try Excel
                if (b"PK" in content[:4]) or (".xlsx" in file_link.lower()) or ("application/vnd.openxmlformats" in ct):
                    if pd is not None:
                        from io import BytesIO
                        try:
                            xls = pd.ExcelFile(BytesIO(content))
                            # use sheet 2 if exists (0-based)
                            sheet_idx = 1 if len(xls.sheet_names) >= 2 else 0
                            df = pd.read_excel(BytesIO(content), sheet_name=sheet_idx)
                            for col in df.columns:
                                if col.strip().lower() == "value":
                                    s = df[col].sum()
                                    try:
                                        return float(s)
                                    except:
                                        return s
                        except Exception:
                            logger.exception("Excel parse failed")
                # Try PDF: extract text and look for numbers (fallback)
                if (".pdf" in file_link.lower() or "application/pdf" in ct) and pdfplumber is not None:
                    try:
                        with pdfplumber.open(io.BytesIO(content)) as pdf:
                            # look at page 2 (1-based)
                            if len(pdf.pages) >= 2:
                                page2 = pdf.pages[1]
                                text = page2.extract_text()
                                # find numbers, sum them if relevant
                                nums = re.findall(r"[-+]?\d*\.\d+|\d+", text.replace(",", ""))
                                if nums:
                                    # Heuristic: sum all numbers (not robust)
                                    vals = [float(x) for x in nums]
                                    return sum(vals)
                    except Exception:
                        logger.exception("PDF parse error")

                # default: return file base64 URI
                return "data:application/octet-stream;base64," + base64.b64encode(content).decode()
            except Exception as e:
                logger.exception("Error downloading file")
                return None

        # If visible_text describes a boolean-ish question
        if re.search(r"\btrue\b|\bfalse\b", visible_text, re.I):
            return True if "true" in visible_text.lower() else False

        # If the page includes a clear numeric question (e.g., "What is 2+2?")
        m = re.search(r"what is ([0-9\+\-\*\/\s\(\)\.]+)\?", visible_text, re.I)
        if m:
            expr = m.group(1)
            try:
                # very careful eval: allow only digits and ops
                if re.fullmatch(r"[\d\.\+\-\*\/\s\(\)]+", expr):
                    return eval(expr)
            except Exception:
                pass

        # Fallback: return a short digest
        snippet = visible_text.strip()[:400]
        return snippet
