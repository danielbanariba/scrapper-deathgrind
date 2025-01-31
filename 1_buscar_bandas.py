from bs4 import BeautifulSoup
import glob

# Obtener una lista de todos los archivos HTML en el directorio
html_files = glob.glob('C:/Users/banar/Downloads/deathgrind_geners/*.html')

# Abrir un archivo en modo de escritura
with open('nombre-de-bandas-encontradas.txt', 'w', encoding='utf-8') as f:
    # Iterar sobre los archivos HTML
    for html_file in html_files:
        # Leer el archivo HTML
        with open(html_file, 'r', encoding='utf-8') as file:
            contents = file.read()

        # Crear un objeto BeautifulSoup con el contenido del archivo
        soup = BeautifulSoup(contents, 'html.parser')

        # Encontrar todos los artículos que contienen la información
        articles = soup.find_all('article', class_='dgc-6v5e1w')

        for article in articles:
            # Encontrar el título del álbum
            album_title = article.find('a', class_='dgc-s4ltpl')
            # Encontrar el nombre de la banda
            band_name = article.find('a', class_='dgc-f2fkwf')
            # Encontrar el div que contiene la información del tipo
            info_div = article.find('div', class_='dgc-upo1hu')
            
            # Solo escribir si todos los elementos necesarios existen
            if album_title and band_name and info_div:
                # Encontrar el tipo dentro del div de información
                release_type = info_div.find('a', href=lambda x: x and '/filter?type=' in x)
                
                if release_type:
                    # Formatear como "Banda - Album [Tipo]"
                    formatted_line = f"{band_name.text} - {album_title.text} [{release_type.text}]\n"
                    f.write(formatted_line)