from bs4 import BeautifulSoup
import time

# Leer el archivo HTML
with open('C:/Users/banar/Downloads/DeathGrindClub.htm', 'r', encoding='utf-8') as f:
    contents = f.read()

# Crear un objeto BeautifulSoup con el contenido del archivo
soup = BeautifulSoup(contents, 'html.parser')

# Encontrar todos los elementos `a` con el atributo `title`
elements = soup.find_all('a', title=True)

# Abrir un archivo en modo de escritura
with open('bandas.txt', 'w', encoding='utf-8') as f:
    # Iterar sobre estos elementos y extraer el valor del atributo `title`
    for element in elements:
        title = element['title']
        # Si el título es "Click to open post", saltar a la siguiente iteración
        if title == 'Click to open post':
            continue
        # Escribir el título en el archivo
        f.write(title + '\n')