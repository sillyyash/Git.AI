from core.parsers.html_parser import parse_html

with open("repos/website/index.html", encoding="utf-8") as f:
    result = parse_html(f.read())

print(result)