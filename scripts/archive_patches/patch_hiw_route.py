#!/usr/bin/env python3
"""Move how-it-works route above if __name__ block."""
from pathlib import Path

f = Path("app.py")
src = f.read_text()

# Remove the misplaced route from the end
src = src.replace('''
@app.route("/how-it-works")
def how_it_works():
    return render_template("how_it_works.html")
''', '')

# Insert it before the if __name__ block
src = src.replace(
    'if __name__ == "__main__":',
    '''@app.route("/how-it-works")
def how_it_works():
    return render_template("how_it_works.html")

if __name__ == "__main__":'''
)

f.write_text(src)
print("[OK] how-it-works route moved above __main__")
