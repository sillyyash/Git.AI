from core.parsers.css_parser import parse_css

with open("test.css", encoding="utf-8") as f:

    result = parse_css(f.read())

print(result)