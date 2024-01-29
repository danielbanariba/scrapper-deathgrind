from bs4 import BeautifulSoup
import glob

# Obtener una lista de todos los archivos HTML en el directorio
html_files = glob.glob('C:/Users/banar/Downloads/deathgrind_geners/*.html')

# Abrir un archivo en modo de escritura
with open('bandas.txt', 'w', encoding='utf-8') as f:
    # Iterar sobre los archivos HTML
    for html_file in html_files:
        # Leer el archivo HTML
        with open(html_file, 'r', encoding='utf-8') as file:
            contents = file.read()

        # Crear un objeto BeautifulSoup con el contenido del archivo
        soup = BeautifulSoup(contents, 'html.parser')

        # Encontrar todos los elementos `a` con el atributo `title`
        elements = soup.find_all('a', title=True)

        # Iterar sobre estos elementos y extraer el valor del atributo `title`
        for element in elements:
            title = element['title']
            # Si el título es "Click to open post" o "Haga clic para abrir la publicación", saltar a la siguiente iteración
            if title == 'Click to open post' or title == 'Haga clic para abrir la publicación':
                continue
            # Escribir el título en el archivo
            f.write(title + '\n')