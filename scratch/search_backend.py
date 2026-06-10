import os

backend_dir = r"c:\Mbm Salud\hipocrafy-backend"
search_terms = ["decrypt", "encrypt", "fernet", "openssl"]

results = []
for root, dirs, files in os.walk(backend_dir):
    dirs[:] = [d for d in dirs if d not in ('vendor', 'node_modules', '.git', 'venv', 'storage', 'bootstrap', 'public')]
    for file in files:
        if file.endswith(".php"):
            path = os.path.join(root, file)
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                    for term in search_terms:
                        if term in content:
                            results.append((path, term))
            except Exception as e:
                pass

print(f"Found {len(results)} matches:")
for path, term in results[:50]:
    print(f"- {path}: matches '{term}'")
