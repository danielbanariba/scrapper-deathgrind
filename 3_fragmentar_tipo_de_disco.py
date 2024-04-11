import os

# Palabras clave
keywords = ["[Demo]", "[Single]", "[Split]", "[Compilation]", "[Promo]", "[Live]", "Demo", "Promo", "Discography"]

# Leer el archivo de bandas aprobadas
with open('bandas.txt', 'r', encoding='utf-8') as f:
    bandas = f.read().splitlines()

# Diccionario para almacenar las bandas por tipo de álbum
bandas_por_tipo = {keyword: [] for keyword in keywords}
bandas_por_tipo["album"] = []  # Agregar categoría para bandas que no coinciden con ninguna palabra clave

# Clasificar las bandas
for banda in bandas:
    matched = False
    for keyword in keywords:
        if keyword in banda:
            bandas_por_tipo[keyword].append(banda)
            matched = True
    if not matched:
        bandas_por_tipo["album"].append(banda)  # Si no hay coincidencia, agregar a "Album"

# Guardar las bandas en archivos
for tipo, bandas in bandas_por_tipo.items():
    # Crear un nombre de archivo válido
    filename = tipo.replace('[', '').replace(']', '').replace(' ', '_') + '.txt'
    with open(filename, 'w', encoding='utf-8') as f:
        for banda in bandas:
            f.write(banda + '\n')
            
os.remove('bandas.txt')