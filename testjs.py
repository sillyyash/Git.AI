from core.parsers.javascript_parser import parse_javascript

with open("test.js", encoding="utf-8") as f:
    result = parse_javascript(f.read())

print(result)