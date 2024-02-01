with open('lista/bandas_corregidos.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

print(f"Leídas {len(lines)} líneas de bandas.txt")

links = []
for line in lines:
    line = line.strip()
    search_query = line.replace(' ', '+')
    url = f"https://www.youtube.com/results?search_query={search_query}"
    link = f'<a href="{url}" target="_blank">{line}</a><br>'
    links.append(link)

print(f"Generados {len(links)} enlaces")

with open('busqueda.html', 'w', encoding='utf-8') as f:
    for link in links:
        f.write(link + '\n')

print("Archivo busqueda.html creado")