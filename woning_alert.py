import os
import json
import hashlib
import smtplib
import urllib.request
from email.message import EmailMessage
from html.parser import HTMLParser
from urllib.parse import urljoin

URL = "https://www.woninghuren.nl/aanbod/te-huur"
MAX_HUUR = 800
MIN_KAMERS = 3  # 2 slaapkamers betekent meestal minimaal 3 kamers

EMAIL_TO = "deanhulman@gmail.com"
EMAIL_FROM = os.environ["EMAIL_USER"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]

STATE_FILE = "bekende_woningen.json"


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            attrs = dict(attrs)
            href = attrs.get("href")
            if href:
                self.current = {
                    "url": urljoin(URL, href),
                    "text": ""
                }

    def handle_data(self, data):
        if self.current:
            self.current["text"] += " " + data.strip()

    def handle_endtag(self, tag):
        if tag == "a" and self.current:
            self.links.append(self.current)
            self.current = None


def download_page(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; WoningAlert/1.0)"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="ignore")


def get_woningen():
    html = download_page(URL)

    parser = LinkParser()
    parser.feed(html)

    woningen = []

    for link in parser.links:
        text = " ".join(link["text"].split())
        url = link["url"]

        # Alleen links naar woningadvertenties proberen te verwerken
        if not text:
            continue

        woningen.append({
            "url": url,
            "text": text
        })

    # Dubbele links verwijderen
    unique = {}
    for woning in woningen:
        unique[woning["url"]] = woning

    return list(unique.values())


def woning_id(woning):
    return hashlib.sha256(
        woning["url"].encode("utf-8")
    ).hexdigest()


def load_known():
    if not os.path.exists(STATE_FILE):
        return set()

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except Exception:
        return set()


def save_known(ids):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, indent=2)


def send_email(nieuwe_woningen):
    msg = EmailMessage()
    msg["Subject"] = f"🏠 {len(nieuwe_woningen)} nieuwe woning(en) op WoningHuren.nl"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    body = [
        "Nieuwe woning(en) gevonden op WoningHuren.nl:",
        ""
    ]

    for woning in nieuwe_woningen:
        body.append(f"🏠 {woning['text']}")
        body.append(f"🔗 {woning['url']}")
        body.append("")

    body.append(
        "Controleer altijd op WoningHuren.nl of de woning "
        "voor jullie passend is."
    )

    msg.set_content("\n".join(body))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_FROM, EMAIL_PASSWORD)
        smtp.send_message(msg)


def main():
    known = load_known()
    woningen = get_woningen()

    nieuwe = []

    for woning in woningen:
        wid = woning_id(woning)

        if wid not in known:
            nieuwe.append(woning)
            known.add(wid)

    save_known(known)

    if nieuwe:
        send_email(nieuwe)
        print(f"{len(nieuwe)} nieuwe woningen gemeld.")
    else:
        print("Geen nieuwe woningen.")


if __name__ == "__main__":
    main()
