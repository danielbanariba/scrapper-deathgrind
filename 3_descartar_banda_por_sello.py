
#?NUEVA IDEA 
# Descargar el html de las pagina DeathGrind.club donde este relacionado el sello discografico y simplemente comparar los nombres y descartarlo automaticamente si pertenece a uno de los sellos discograficos mencionados anteriormente

# 
#TODO descargar el html de las paginas de DeathGrind.club donde este relacionado el sello discografico
# Century Media Records = https://deathgrind.club/posts/labels/Century%20Media%20Records
# Nuclear Blast Records = https://deathgrind.club/posts/labels/Nuclear%20Blast%20Records
# https://deathgrind.club/posts/labels/Nuclear%20Blast
# Metal Blade Records = https://deathgrind.club/posts/labels/Metal%20Blade%20Records
# Unique Leader Records = https://deathgrind.club/posts/labels/Unique%20Leader%20Records
# Season of Mist = https://deathgrind.club/posts/labels/Season%20of%20Mist
# Problematic Records = https://deathgrind.club/posts/labels/Problematic%20Records 
# Willowtip Records = https://deathgrind.club/posts/labels/Willowtip%20Records
# Ungodly Ruins Productions = https://deathgrind.club/posts/labels/Ungodly%20Ruins%20Productions
# Comatose Music = https://deathgrind.club/posts/labels/Comatose%20Music
# My Kingdom Music = https://deathgrind.club/posts/labels/My%20Kingdom%20Music
# Violent Journey Records = https://deathgrind.club/posts/labels/Violent%20Journey%20Records
# Carnage BRA Records
# Detest 
# Metal Age Productions = https://deathgrind.club/posts/labels/Metal%20Age%20Productions
# Artistfy Music = https://deathgrind.club/posts/labels/Artistfy%20Music
# Copro Records = https://deathgrind.club/posts/labels/Copro%20Records
# DIY PROD = https://deathgrind.club/posts/labels/DIY%20PROD
# Agonia Records = https://deathgrind.club/posts/labels/Agonia%20Records
# Albergue Estudio = https://deathgrind.club/posts/labels/Albergue%20Estudio
# Altafonte Network S.L. = https://deathgrind.club/posts/labels/Altafonte%20Network%20S.L.
# Artistfy Music = https://deathgrind.club/posts/labels/Artistfy%20Music
# Baphomet Records = https://deathgrind.club/posts/labels/Baphomet%20Records
# CCP Records = https://deathgrind.club/posts/labels/CCP%20Records
# Carnage BRA Records = https://deathgrind.club/posts/labels/Carnage%20BRA%20Records
# Century Media Records  = https://deathgrind.club/posts/labels/Century%20Media%20Records
# Comatose Music  = https://deathgrind.club/posts/labels/Comatose%20Music
# Copro Records = https://deathgrind.club/posts/labels/Copro%20Records
# Dark Descent Records = https://deathgrind.club/posts/labels/Dark%20Descent%20Records
# DIY PROD = https://deathgrind.club/posts/labels/DIY%20PROD
# Demonhood Productions = https://deathgrind.club/posts/labels/Demonhood%20Productions
# Dissident Records = https://deathgrind.club/posts/labels/Dissident%20Records
# Detest = https://deathgrind.club/posts/labels/Detest
# Firebox Music = https://deathgrind.club/posts/labels/Firebox%20Music
# Metal Age Productions  = https://deathgrind.club/posts/labels/Metal%20Age%20Productions
# Metal Blade Records Records = https://deathgrind.club/posts/labels/Metal%20Blade%20Records
# My Kingdom Music = https://deathgrind.club/posts/labels/My%20Kingdom%20Music
# My Fate Music = https://deathgrind.club/posts/labels/My%20Fate%20Music
# Metal Age Productions = https://deathgrind.club/posts/labels/Metal%20Age%20Productions
# Nuclear War Now   = https://deathgrind.club/posts/labels/Nuclear%20War%20Now
# Nuclear Blast Records = https://deathgrind.club/posts/labels/Nuclear%20Blast%20Records
# Ungodly Ruins Productions     = https://deathgrind.club/posts/labels/Ungodly%20Ruins%20Productions
# Unique Leader Records     = https://deathgrind.club/posts/labels/Unique%20Leader%20Records
# Season of Mist    = https://deathgrind.club/posts/labels/Season%20of%20Mist
# Problematic Records   = https://deathgrind.club/posts/labels/Problematic%20Records
# Woodcut Records   = https://deathgrind.club/posts/labels/Woodcut%20Records
# Willowtip Records     = https://deathgrind.club/posts/labels/Willowtip%20Records
# Violent Journey Records   = https://deathgrind.club/posts/labels/Violent%20Journey%20Records
# Red Stream Records    = https://deathgrind.club/posts/labels/Red%20Stream%20Records
# Listenable records    = https://deathgrind.club/posts/labels/Listenable%20records
# Lifeforce Records   = https://deathgrind.club/posts/labels/Lifeforce%20Records
# Ibex Moon Records  = https://deathgrind.club/posts/labels/Ibex%20Moon%20Records
# Scarlet Records   = https://deathgrind.club/posts/labels/Scarlet%20Records
# Napalm Records = https://deathgrind.club/posts/labels/Napalm%20Records

import webbrowser

# urls = [
#     "https://deathgrind.club/posts/labels/Napalm%20Records",
#     "https://deathgrind.club/posts/labels/Century%20Media%20Records",
#     "https://deathgrind.club/posts/labels/Nuclear%20Blast",
#     "https://deathgrind.club/posts/labels/Nuclear%20Blast%20Records",
#     "https://deathgrind.club/posts/labels/Metal%20Blade%20Records",
#     "https://deathgrind.club/posts/labels/Unique%20Leader%20Records",
#     "https://deathgrind.club/posts/labels/Season%20of%20Mist",
#     "https://deathgrind.club/posts/labels/Problematic%20Records",
#     "https://deathgrind.club/posts/labels/Willowtip%20Records",
#     "https://deathgrind.club/posts/labels/Ungodly%20Ruins%20Productions",
#     "https://deathgrind.club/posts/labels/Comatose%20Music",
#     "https://deathgrind.club/posts/labels/My%20Kingdom%20Music",
#     "https://deathgrind.club/posts/labels/Violent%20Journey%20Records",
#     "https://deathgrind.club/posts/labels/Carnage%20BRA%20Records",
#     "https://deathgrind.club/posts/labels/Detest",
#     "https://deathgrind.club/posts/labels/Metal%20Age%20Productions",
#     "https://deathgrind.club/posts/labels/Artistfy%20Music",
#     "https://deathgrind.club/posts/labels/Copro%20Records",
#     "https://deathgrind.club/posts/labels/DIY%20PROD",
#     "https://deathgrind.club/posts/labels/Agonia%20Records",
#     "https://deathgrind.club/posts/labels/Albergue%20Estudio",
#     "https://deathgrind.club/posts/labels/Altafonte%20Network%20S.L.",
#     "https://deathgrind.club/posts/labels/Baphomet%20Records",
#     "https://deathgrind.club/posts/labels/CCP%20Records",
#     "https://deathgrind.club/posts/labels/Carnage%20BRA%20Records",
#     "https://deathgrind.club/posts/labels/Dark%20Descent%20Records",
#     "https://deathgrind.club/posts/labels/Demonhood%20Productions",
#     "https://deathgrind.club/posts/labels/Dissident%20Records",
#     "https://deathgrind.club/posts/labels/Detest",
#     "https://deathgrind.club/posts/labels/Firebox%20Music",
#     "https://deathgrind.club/posts/labels/Nuclear%20War%20Now",
#     "https://deathgrind.club/posts/labels/Woodcut%20Records",
#     "https://deathgrind.club/posts/labels/Red%20Stream%20Records",
#     "https://deathgrind.club/posts/labels/Listenable%20records",
#     "https://deathgrind.club/posts/labels/Lifeforce%20Records",
#     "https://deathgrind.club/posts/labels/Ibex%20Moon%20Records",
#     "https://deathgrind.club/posts/labels/Scarlet%20Records",
# ]

# for url in urls:
#     webbrowser.open(url)

#Va a buscar todas las bandas en el archivo html y las va a guardar en un archivo de texto

from bs4 import BeautifulSoup
import glob
import os

# Obtener una lista de todos los archivos HTML en el directorio
html_files = glob.glob('C:/Users/banar/Downloads/discografica/*.html')

# Abrir un archivo en modo de escritura
with open('bandas-copyright.txt', 'w', encoding='utf-8') as f:
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

# Leer el contenido de bandas-copyright.txt
with open('bandas-copyright.txt', 'r', encoding='utf-8') as f:
    copyright_lines = set(f.read().splitlines())

# Leer el contenido de bandas.txt
with open('bandas.txt', 'r', encoding='utf-8') as f:
    bandas_lines = set(f.read().splitlines())

# Encontrar duplicados (intersección) y eliminarlos de bandas.txt
bandas_lines = bandas_lines - copyright_lines

# Escribir las líneas sin duplicados de vuelta en bandas.txt
with open('bandas.txt', 'w', encoding='utf-8') as f:
    for line in sorted(bandas_lines):  # Opcional: ordenar las líneas antes de escribirlas
        f.write(line + '\n')