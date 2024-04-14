from bs4 import BeautifulSoup
import glob

# Leer el archivo y almacenar los nombres en una lista
with open('bandas-aprobadas.txt', 'r', encoding='utf-8') as f:
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

    # Buscar todos los elementos 'a' con el atributo 'title'
    elements = soup.find_all('a', title=True)

    # Para cada elemento encontrado
    for element in elements:
        title = element['title']
        # Si el título contiene alguno de los nombres
        for name in names:
            if name == title:  # Cambiar a la comparación exacta
                # Extraer el atributo 'href' y almacenarlo
                links.append((title, element.get('href')))
                names.remove(name)  # Eliminar el nombre de la lista
                break  # Salir del bucle una vez que se encuentra una coincidencia

# Escribir todos los enlaces encontrados en el archivo 'links_bandas.html'
with open('links_bandas.html', 'w', encoding='utf-8') as f:
    for title, link in links:
        f.write(f'<a href="{link}" target="_blank">{title}</a><br>\n')