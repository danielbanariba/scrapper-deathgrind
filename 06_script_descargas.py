from bs4 import BeautifulSoup
import glob

# Leer el archivo 'aprobadas.txt' y almacenar los nombres en una lista
with open('bandas_sin_keywords.txt', 'r', encoding='utf-8') as f:
    names = [line.strip() for line in f]

# Inicializar una lista para almacenar los enlaces encontrados
links = []

# Obtener una lista de todos los archivos HTML en el directorio
html_files = glob.glob('C:/Users/banar/Downloads/deathgrind_geners/*.html')

# Para cada archivo HTML en la lista
for filename in html_files:
    print(f"Processing {filename}")  # Agregar esta línea
    # Abrir el archivo y analizar el contenido con BeautifulSoup
    with open(filename, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')

    # Buscar todos los elementos con la etiqueta 'h3' y la clase 'dgc-ljodyg etdg1c916'
    elements = soup.find_all('h3', {'class': 'dgc-ljodyg etdg1c916'})

    # Para cada elemento encontrado
    for element in elements:
        # Buscar la etiqueta 'a'
        a_tag = element.find('a')

        # Si el título coincide exactamente
        if a_tag:
            title = a_tag.get('title')
            print(f"Comparing title: {title}")  # Agregar esta línea
            if title in names:
                # Extraer el atributo 'href' y almacenarlo
                links.append(a_tag.get('href'))

# Escribir todos los enlaces encontrados en el archivo 'links_bandas.txt'
with open('links_bandas.txt', 'w', encoding='utf-8') as f:
    for link in links:
        f.write(f"{link}\n")