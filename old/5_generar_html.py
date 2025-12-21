# Genera un archivo HTML con enlaces a YouTube de las canciones para poder facilitar la búsqueda de las mismas.

with open('album.txt', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Genera los enlaces a YouTube del archivo album-ep.txt
links = []
for line in lines:
    line = line.strip()
    search_query = line.replace(' ', '+')
    url = f"https://www.youtube.com/results?search_query={search_query}"
    link = f'<a href="{url}" target="_blank">{line}</a><br>'
    links.append(link)

print(f"{len(links)} enlaces generados")

with open('busqueda.html', 'w', encoding='utf-8') as f:
    for link in links:
        f.write(link + '\n')