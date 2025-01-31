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
    print(f"Processing {filename}")
    
    # Abrir el archivo y analizar el contenido con BeautifulSoup     
    with open(filename, 'r', encoding='utf-8') as f:         
        soup = BeautifulSoup(f, 'html.parser')      

    # Encontrar todos los artículos que contienen la información
    articles = soup.find_all('article', class_='dgc-6v5e1w')

    for article in articles:
        # Encontrar el título del álbum y la banda
        album_title = article.find('a', class_='dgc-s4ltpl')
        band_name = article.find('a', class_='dgc-f2fkwf')
        
        if album_title and band_name:
            # Formatear como "Banda - Album"
            title = f"{band_name.text} - {album_title.text}"
            
            # Verificar si este título está en nuestra lista de nombres
            if title in names:
                # Obtener el enlace del título del álbum
                link = album_title.get('href')
                if link:
                    # Agregar el enlace completo si es una URL relativa
                    if link.startswith('/'):
                        link = 'https://deathgrind.club' + link
                    links.append((title, link))
                    names.remove(title)  # Eliminar el nombre de la lista
                    
# Escribir todos los enlaces encontrados en el archivo 'links_bandas.html' 
with open('links_bandas.html', 'w', encoding='utf-8') as f:     
    for title, link in links:         
        f.write(f'<a href="{link}" target="_blank">{title}</a><br>\n')

# Opcionalmente, imprimir nombres que no se encontraron
if names:
    print("\nNombres que no se encontraron:")
    for name in names:
        print(name)