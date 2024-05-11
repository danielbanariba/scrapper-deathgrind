# Elimina los duplicados de un archivo de texto y guarda el resultado en un nuevo archivo

# import os
# import re

# # Leer el archivo
# with open('bandas-subidas-al-canal.txt', 'r', encoding='utf-8') as f:
#     lines = f.read().splitlines()

# # Eliminar duplicados convirtiendo las líneas en un conjunto
# lines = list(set(lines))

# # Escribir las líneas de nuevo en el archivo
# with open('bandas-daniel-banariba.txt', 'w', encoding='utf-8') as f:
#     for line in lines:
#         f.write(line + '\n')

# # Eliminar el archivo original
# os.remove('bandas-subidas-al-canal.txt')

import os
import re

# Función para limpiar el texto eliminando contenido entre paréntesis
def limpiar_texto(linea):
    return re.sub(r"\s*\([^)]*\)", "", linea).strip()

# Leer el contenido de ambos archivos
with open('bandas-daniel-banariba.txt', 'r', encoding='utf-8') as file:
    bandas_daniel = file.readlines()

with open('bandas.txt', 'r', encoding='utf-8') as file:
    bandas = file.readlines()

# Limpiar y extraer los nombres de las bandas y álbumes
bandas_daniel_info = {limpiar_texto(line): line for line in bandas_daniel}
bandas_info = {limpiar_texto(line) for line in bandas}

# Encontrar los elementos únicos en bandas_daniel_info
info_unicos = set(bandas_daniel_info.keys()) - bandas_info

# Preparar las líneas a escribir manteniendo el formato original
lineas_a_escribir = [bandas_daniel_info[info] for info in info_unicos]

# Reescribir el archivo bandas-daniel-banariba.txt con las líneas que no tienen coincidencias
with open('bandas-daniel-banariba.txt', 'w', encoding='utf-8') as file:
    for linea in lineas_a_escribir:
        file.write(linea)

# Opcional: Eliminar el archivo original si es necesario
# os.remove('bandas-subidas-al-canal.txt')