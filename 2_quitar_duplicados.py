# Elimina los duplicados de un archivo de texto y guarda el resultado en un nuevo archivo

import os

# Leer el archivo
with open('nombre-de-bandas-encontradas.txt', 'r', encoding='utf-8') as f:
    lines = f.read().splitlines()

# Eliminar duplicados convirtiendo las líneas en un conjunto
lines = list(set(lines))

# Escribir las líneas de nuevo en el archivo
with open('bandas.txt', 'w', encoding='utf-8') as f:
    for line in lines:
        f.write(line + '\n')

# Eliminar el archivo original
os.remove('nombre-de-bandas-encontradas.txt')