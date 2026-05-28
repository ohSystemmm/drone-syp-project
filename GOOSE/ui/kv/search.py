filepath = r'C:\Users\Quark\PycharmProjects\GOOSE\GOOSE\ui\media_gallery.py'

with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'toggle_selection_mode' in line:
        print(f"{i+1}: {line.strip()}")
