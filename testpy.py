from core.parsers.python_parser import parse_python

with open("test.py", encoding="utf-8") as f:
    result = parse_python(f.read())

print(result)